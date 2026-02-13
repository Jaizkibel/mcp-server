from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import subprocess
import asyncio
from typing import AsyncIterator

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

import yaml

from utils.helpers import (
    get_companion_path,
    get_content_from_zip,
    get_gradle_jar,
    init_logging,
    get_maven_jar,
    decompile_from_jar,
)
from utils.args import parse_arguments
from utils.mcp_helpers import get_project_folder, is_relative_path, to_text_context
from utils.web import (
    CustomJSONEncoder,
    close_http_client,
    http_client_context,
    strip_strong_tags,
    strip_text_from_html,
)

# Configure logging
init_logging("log", "mcp_server.log")

logger = logging.getLogger(__name__)

rootPath: Path = Path(__file__).parent
configPath: str = f"{Path.home()}/.mcp-server/config.yml"
config = {}


@asynccontextmanager
async def server_lifespan(_: Server) -> AsyncIterator[dict]:
    """Manage server startup and shutdown lifecycle."""
    # Minimal implementation that yields empty dict
    # Server parameter is not used here
    try:
        yield {}
    finally:
        await cleanup()


# Pass lifespan to server
server = Server("low-level-server", lifespan=server_lifespan)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Lists all available tools."""
    logger.debug("Collecting tools")
    tools = [
        types.Tool(
            name="web_search",
            description="Search the web for information using the Brave search API. Returns a JSON string containing the URLs, descriptions, and fetched content of the top 3 results. The HTML content is converted to markdown",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search string"}
                },
                "required": ["query"],
            },
            annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        ),
        types.Tool(
            name="open_in_browser",
            description="Opens a url or file in the local browser. Returns a success or error message.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL or file path to open.",
                    }
                },
                "required": ["url"],
            },
            annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        ),
        types.Tool(
            name="http_get_request",
            description="Makes an HTTP GET request to the specified URL with optional headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to send the GET request to.",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Map of request headers.",
                    },
                },
                "required": ["url"],
            },
            annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        ),
    ]

    if config.get("buildTool") is not None:
        logger.debug("Adding build related tools")
        tools.append(
            types.Tool(
                name="get_source",
                description="Returns the source of a Java class. Does not work with classes from Java standard libraries.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "class_name": {
                            "type": "string",
                            "description": "The full class name. Example: 'java.util.List'",
                        }
                    },
                    "required": ["class_name"],
                },
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, openWorldHint=False
                ),
            )
        )
        tools.append(
            types.Tool(
                name="get_javadoc",
                description="Gets Javadoc for a class. Does not work with classes from Java standard libraries.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "class_name": {
                            "type": "string",
                            "description": "The full class name. Example: 'java.util.List'",
                        }
                    },
                    "required": ["class_name"],
                },
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, openWorldHint=False
                ),
            )
        )

    logger.debug("Collected %d tools", len(tools))
    return tools


# Tool registry with configuration for each tool
TOOL_REGISTRY = {
    "web_search": {
        "handler": lambda args: web_search(args["query"]),
        "required_params": ["query"],
    },
    "open_in_browser": {
        "handler": lambda args: open_in_browser(args["url"]),
        "required_params": ["url"],
    },
    "http_get_request": {
        "handler": lambda args: http_get_request(args["url"], args.get("headers")),
        "required_params": ["url"],
    },
    "get_source": {
        "handler": lambda args: get_source(args["class_name"]),
        "required_params": ["class_name"],
    },
    "get_javadoc": {
        "handler": lambda args: get_javadoc(args["class_name"]),
        "required_params": ["class_name"],
    },
}


def validate_tool_arguments(tool_name: str, arguments: dict) -> None:
    """Validate that all required parameters are present for a tool.

    Args:
        tool_name: Name of the tool to validate
        arguments: Dictionary of arguments provided

    Raises:
        ValueError: If tool is not found or required parameters are missing
    """
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found")

    tool_config = TOOL_REGISTRY[tool_name]
    required_params = tool_config["required_params"]

    for param in required_params:
        if param not in arguments or arguments[param] is None:
            raise ValueError(f"Parameter '{param}' is missing")


@server.call_tool()
async def handle_tool_call(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle all tool calls using the tool registry pattern."""

    try:
        logger.debug("handling tool '%s' with args %s", name, arguments)

        # Validate tool exists and has required parameters
        validate_tool_arguments(name, arguments)

        # Get tool configuration and execute handler
        tool_config = TOOL_REGISTRY[name]
        handler = tool_config["handler"]

        # Execute the tool handler
        response = await handler(arguments)

    except Exception as e:
        logger.error(
            "Error handling tool call '%s': %s", name, arguments, exc_info=True
        )
        response = json.dumps({"error": f"Error handling tool call '{name}': {str(e)}"})

    return to_text_context(response)


async def http_get_request(url: str, headers: dict = None) -> str:
    """Makes an HTTP GET request to the specified URL with optional headers.
    This is a read-only operation that retrieves data from a web service.

    Args:
        url (str): The URL to send the GET request to.
        headers (dict, optional): Dictionary of HTTP headers to include. Defaults to None.

    Returns:
        str: A JSON string containing the response status, headers, and body, or an error message.
    """
    logger.info("Making GET request to: %s", url)
    if url.startswith("http://"):
        logger.error("Invalid URL: %s. URL must start with 'https://'.", url)
        return json.dumps({"error": "Invalid URL. Must start with 'https://'."})

    try:
        async with http_client_context() as client:
            response = await client.get(url, headers=headers or {})
            response.raise_for_status()
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
            return json.dumps(result, cls=CustomJSONEncoder)
    except Exception as e:
        logger.error("Unexpected error in http_get_request: %s", e, exc_info=True)
        return json.dumps({"error": f"Unexpected server error: {str(e)}"})


async def web_search(query: str) -> str:
    """Executes a search query using the Brave Search API and fetches content from the 3 top results"""
    MAX_SEARCH_RESULTS = (
        10  # higher than number of results to return because request may fail
    )
    MAX_RESULTS_TO_RETURN = 5
    MAX_RESULT_LENGTH = 10000
    logger.info("Executing web query: %s", query)
    url = config["braveSearch"]["apiUrl"]
    brave_api_key = config["braveSearch"]["apiKey"]
    if not brave_api_key:
        logger.error("Brave API key is missing in the code.")
        return json.dumps(
            {"error": "Server configuration error: Brave API key missing."}
        )

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": brave_api_key,
    }
    params = {"result_filter": "web", "count": MAX_SEARCH_RESULTS, "q": query}

    async def fetch_url_content(meta: dict) -> dict:
        """Helper function to fetch content for a single URL."""
        if "url" not in meta:
            logger.warning("Meta dictionary missing 'url' key.")
            meta["error"] = "Missing URL in search result"
            return meta
        try:
            logger.info("Fetching content from: %s", meta["url"])
            async with http_client_context() as client:
                response = await client.get(meta["url"])
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    # markdown converter is not as good as expected
                    # text = html_to_markdown(response.content)
                    text = strip_text_from_html(response.content)
                    meta["content"] = text[:MAX_RESULT_LENGTH]
                    logger.info(
                        "Successfully fetched and processed content from %s",
                        meta["url"],
                    )
                else:
                    logger.warning(
                        "Skipping non-HTML content (%s) from %s",
                        content_type,
                        meta["url"],
                    )
                    meta["error"] = f"Skipped non-HTML content ({content_type})"
                return meta
        except Exception as e:
            logger.error(
                "Failed to fetch or process %s: %s",
                meta.get("url", "unknown URL"),
                e,
                exc_info=True,
            )
            meta["error"] = f"General error: {str(e)}"
            return meta

    try:
        async with http_client_context() as client:
            logger.info(
                "Sending request to Brave API (%s) with query: '%s'",
                url,
                query,
            )
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            json_response = response.json()
            logger.info("Received response from Brave API.")

            metas = []
            results = json_response.get("web", {}).get("results", [])
            if not results:
                logger.warning("No web results found for query: '%s'", query)

            for result in results:
                if url := result.get("url"):
                    meta = {
                        "url": url,
                        "description": strip_strong_tags(
                            result.get("description", "No description available.")
                        ),
                    }
                    metas.append(meta)
                else:
                    logger.warning("Search result missing 'url': %s", result)

            logger.info("Extracted %d URLs to fetch content from.", len(metas))
            findings = (
                await asyncio.gather(*[fetch_url_content(meta) for meta in metas])
                if metas
                else []
            )
            # remove errors
            filtered_findings = [f for f in findings if f.get("error") is None]
            logger.info("Finished fetching content for all URLs.")
            # do only return the most relevant findings
            return json.dumps(
                filtered_findings[:MAX_RESULTS_TO_RETURN], cls=CustomJSONEncoder
            )

    except Exception as e:
        logger.error("An unexpected error occurred in query_web: %s", e, exc_info=True)
        return json.dumps({"error": f"Unexpected server error: {str(e)}"})


async def open_in_browser(url: str) -> str:
    """Opens a url or file in the local browser"""
    if not url.endswith(".html"):
        return "Error: can open HTML pages only"
    workspace_path = await get_project_folder(server, config)
    if not workspace_path:
        logger.error("Workspace path is not set in the configuration.")
        return "Error: Workspace path is not set in the configuration."
    browser_command = config.get("browserCommand")
    if not browser_command:
        logger.error("Browser command is not set in the configuration.")
        return "Error: Browser command is not set in the configuration."

    if is_relative_path(url):
        url = f"{workspace_path}/{url}"

    try:
        # Execute command to open browser
        # Popen returns immediately after executing command
        subprocess.Popen(
            [browser_command, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return "Browser successfully opened"
    except Exception as e:
        logger.error("Error opening url in browser: %s", e, exc_info=True)
        return f"Error: {str(e)}"


async def get_source(class_name: str) -> str:
    """Decompiles a Java class and returns the source code."""

    build_tool: str = config.get("buildTool")
    if build_tool is None:
        return "Error: Build tool not defined."

    workspace_path = await get_project_folder(server, config)
    if not workspace_path:
        logger.error("Workspace path is not set in the configuration.")
        return "Error: Workspace path is not set in the configuration."

    # search for lib jar containing the class
    if "mvn" in build_tool:
        jar_path = get_maven_jar(build_tool, class_name, workspace_path)
    elif "gradle" in build_tool:
        jar_path = get_gradle_jar(build_tool, class_name, workspace_path)
    else:
        return f"Error: Build tool {build_tool} is not supported"

    if jar_path is None:
        return f"Error: No source for class {class_name} found"

    # try source jar first, maybe it is downloaded
    # to download all source jars, use 'mvn dependency:sources'
    zip_path = get_companion_path(build_tool, jar_path, "sources")
    if zip_path is not None:
        # Convert class name to path (com.example.MyClass → com/example/MyClass.java)
        java_file = class_name.replace(".", "/") + ".java"
        content = get_content_from_zip(zip_path, java_file)
        if content is None:
            return f"Error: No doc file for {java_file} found in {zip_path}"
        logger.info("Found Java source in sources jar %s", zip_path)
        return content

    # fallback: decompile
    return decompile_from_jar(class_name, jar_path, rootPath, workspace_path)


async def get_javadoc(class_name: str) -> str:
    """Gets Javadoc for class.

    Works with downloaded Javadoc jars only.
    Use 'mvn dependency:resolve -Dclassifier=javadoc' to download them.
    """

    build_tool: str = config.get("buildTool")
    if build_tool is None:
        return "Error: Build tool not defined."

    workspace_path = await get_project_folder(server, config)
    if not workspace_path:
        logger.error("Workspace path is not set in the configuration.")
        return "Error: Workspace path is not set in the configuration."

    if "mvn" in build_tool:
        jar_path = get_maven_jar(build_tool, class_name, workspace_path)
    elif "gradle" in build_tool:
        jar_path = get_gradle_jar(build_tool, class_name, workspace_path)
    else:
        return f"Error: Build tool {build_tool} is not supported"

    # lookup corresponding javadoc file (zipped)
    zip_path = get_companion_path(build_tool, jar_path, "javadoc")
    if zip_path is None:
        return f"Error: No javadoc jar found for class {class_name}"

    # Convert class name to path (com.example.MyClass → com/example/MyClass.html)
    html_file = class_name.replace(".", "/") + ".html"
    content = get_content_from_zip(zip_path, html_file)
    if content is None:
        return f"Error: No doc file for {html_file} found in {zip_path}"

    return content


async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="low-level",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


async def cleanup():
    """Cleanup resources when the server stops."""
    await close_http_client()
    logger.info("Cleanup completed.")


if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_arguments()
    logger.info("Command-line arguments: %s", args)

    env = os.environ.copy()
    logger.info("Environment variables: %s", env)

    # Load config at startup
    try:
        with open(configPath, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
        # Set current workspace foldername
        if args.project_folder is not None:
            config["projectFolder"] = args.project_folder
        # Set Java build tool
        if args.build_tool is not None:
            config["buildTool"] = args.build_tool
        logger.info("Successfully loaded server configuration %s", config)
    except Exception as e:
        logger.error("Failed to load config: %s", e, exc_info=True)
        config = {}

    asyncio.run(run())
