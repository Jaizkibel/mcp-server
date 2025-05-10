from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import platform
from typing import AsyncIterator

import mcp.server.stdio
import mcp.types as types

# from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import logging

import yaml

from utils.args import parse_arguments
from utils.mcp import to_text_context
from utils.web import (
    CustomJSONEncoder,
    http_client_context,
    strip_strong_tags,
    strip_text_from_html,
)

# Configure logging
logging.basicConfig(
    filename="mcp_server_low.log",
    level=logging.NOTSET,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

configPath = f"{Path.home()}/.mcp-server/config.yml"
config = {}


@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[dict]:
    """Manage server startup and shutdown lifecycle."""
    # Minimal implementation that yields empty dict
    yield {}


# Pass lifespan to server
server = Server("low-level-server", lifespan=server_lifespan)

# Access lifespan context in handlers
# @server.call_tool()
# async def query_db(name: str, arguments: dict) -> list:
#     ctx = server.request_context
#     db = ctx.lifespan_context["db"]
#     return await db.query(arguments["query"])


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Lists all available tools."""
    return [
        types.Tool(
            name="get_os_info",
            description="Get information about the local operating system. Rturns a JSON string containing detailed OS information.",
            inputSchema={"type": "object", "required": []},
            annotations={"readOnlyHint": True},
        ),
        types.Tool(
            name="web_search",
            description="Search the web for information using the Brave search API. Returns a JSON string containing the URLs, descriptions, and fetched content of the top 3 results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search string"}
                },
                "required": ["query"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
    ]

@server.call_tool()
async def handle_tool_call(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """handles all tool calls"""

    response = f"Error: Tool {name} not found"
    if name == "get_os_info":
        response = await get_os_info()
    if name == "web_search":
        query = arguments["query"]
        response = await web_search(query)

    return to_text_context(response)        


async def get_os_info() -> str:
    """Get information about the local operating system"""
    logger.info("get_os_info called")

    os_info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }

    # Get additional info based on the platform
    if platform.system() == "Windows":
        os_info["edition"] = (
            platform.win32_edition() if hasattr(platform, "win32_edition") else "N/A"
        )
        os_info["is_64bit"] = platform.machine().endswith("64")
    elif platform.system() in ["Darwin", "Linux"]:
        try:
            uname_result = os.uname()
            os_info["node"] = uname_result.nodename
            os_info["kernel"] = uname_result.release
        except AttributeError:
            pass

    logger.info(f"Collected OS info: {os_info}")
    return json.dumps(os_info, cls=CustomJSONEncoder)


async def web_search(query: str) -> str:
    """Executes a search query using the Brave Search API and fetches content from the 3 top results"""
    logger.info(f"Executing web query: {query}")
    url = config["braveSearch"]["apiUrl"]
    brave_api_key = config["braveSearch"]["apiKey"]
    if not brave_api_key:
        logger.error("Brave API key is missing in the code.")
        return json.dumps({"error": "Server configuration error: Brave API key missing."})

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": brave_api_key,
    }
    params = {"result_filter": "web", "count": 3, "q": query}

    async def fetch_url_content(meta: dict) -> dict:
        """Helper function to fetch content for a single URL."""
        if "url" not in meta:
            logger.warning("Meta dictionary missing 'url' key.")
            meta["error"] = "Missing URL in search result"
            return meta
        try:
            logger.info(f"Fetching content from: {meta['url']}")
            async with http_client_context() as client:
                response = await client.get(meta["url"])
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    text = strip_text_from_html(response.content)
                    meta["content"] = text[:10000]
                    logger.info(
                        f"Successfully fetched and processed content from {meta['url']}"
                    )
                else:
                    logger.warning(
                        f"Skipping non-HTML content ({content_type}) from {meta['url']}"
                    )
                    meta["content"] = f"Skipped non-HTML content ({content_type})"
                return meta
        except Exception as e:
            logger.error(
                f"Failed to fetch or process {meta.get('url', 'unknown URL')}: {e}",
                exc_info=True,
            )
            meta["error"] = f"General error: {str(e)}"
            return meta

    try:
        async with http_client_context() as client:
            logger.info(f"Sending request to Brave API ({url}) with query: '{query}'")
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            json_response = response.json()
            logger.info("Received response from Brave API.")

            metas = []
            results = json_response.get("web", {}).get("results", [])
            if not results:
                logger.warning(f"No web results found for query: '{query}'")

            for result in results:
                if url := result.get("url"):
                    meta = {"url": url}
                    meta["description"] = strip_strong_tags(
                        result.get("description", "No description available.")
                    )
                    metas.append(meta)
                else:
                    logger.warning(f"Search result missing 'url': {result}")

            logger.info(f"Extracted {len(metas)} URLs to fetch content from.")
            findings = (
                await asyncio.gather(*[fetch_url_content(meta) for meta in metas])
                if metas
                else []
            )
            logger.info("Finished fetching content for all URLs.")
            return json.dumps(findings, cls=CustomJSONEncoder)

    except Exception as e:
        logger.error(f"An unexpected error occurred in query_web: {e}", exc_info=True)
        return json.dumps({"error": f"Unexpected server error: {str(e)}"})


async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="low-level",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    # Parse command-line arguments
    args = parse_arguments()
    logger.info(f"Command-line arguments: {args}")

    # Load config at startup
    try:
        with open(configPath, "r") as file:
            config = yaml.safe_load(file)
        # Set DB Name of Database to connect to
        if not args.db_name is None:
            config["dbName"] = args.db_name
        # Set current workspace foldername
        if not args.project_folder is None:
            config["projectFolder"] = args.project_folder
        logger.info(f"Successfully loaded server configuration {config}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        config = {}

    asyncio.run(run())
