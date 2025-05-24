from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import asyncio
from typing import AsyncIterator

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import logging

import yaml

from utils.helpers import init_logging
from utils.args import parse_arguments
from utils.db import close_db_pool, db_connection_context
from utils.mcp import get_project_folder, is_relative_path, to_text_context
from utils.web import (
    CustomJSONEncoder,
    close_http_client,
    html_to_markdown,
    http_client_context,
    strip_strong_tags,
    strip_text_from_html,
)

# Configure logging
init_logging("log", "mcp_server.log")

logger = logging.getLogger(__name__)

configPath = f"{Path.home()}/.mcp-server/config.yml"
config = {}


@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[dict]:
    """Manage server startup and shutdown lifecycle."""
    # Minimal implementation that yields empty dict
    try:
        yield {}
    finally:
        asyncio.run(cleanup())


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
            name="web_search",
            description="Search the web for information using the Brave search API. Returns a JSON string containing the URLs, descriptions, and fetched content of the top 3 results. The HTML content is coneverted to markdown",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search string"}
                },
                "required": ["query"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
        types.Tool(
            name="open_in_browser",
            description="Opens a url or file in the local browser .Returns a success or error message.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL or file path to open."}
                },
                "required": ["url"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
        types.Tool(
            name="run_maven_tests",
            description="Runs Maven tests. Executes 'mvn test -q -Dtest=<test_pattern> surefire-report:report'",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_pattern": {"type": "string", "description": "The pattern matching test files to execute"}
                },
                "required": ["test_pattern"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
        types.Tool(
            name="run_gradle_tests",
            description="Runs Gradle tests. Executes 'gradlew test -tests <test_pattern>'",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_pattern": {"type": "string", "description": "The pattern matching test files to execute"}
                },
                "required": ["test_pattern"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
        types.Tool(
            name="execute_sql_query",
            description="Executes a read-only SQL query on a PostgreSQL database and returns the result as JSON.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {"type": "string", "description": "The name of the database to connect."},
                    "query": {"type": "string", "description": "The SQL query to execute"}
                },
                "required": ["dbname","query"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": False},
        ),
        types.Tool(
            name="http_get_request",
            description="Makes an HTTP GET request to the specified URL with optional headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to send the GET request to."},
                    "headers": {"type": "object", "description": "Map of request headers."}
                },
                "required": ["url"],
            },
            annotations={"readOnlyHint": True, "openWorldHint": True},
        ),
    ]

@server.call_tool()
async def handle_tool_call(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """handles all tool calls!!!"""

    response = f"Error: Tool {name} not found"
    if name == "web_search":
        query = arguments["query"]
        if query == None:
            ValueError("Parameter 'query' is missing")
        response = await web_search(query)
    if name == "open_in_browser":
        url = arguments["url"]
        if url == None:
            ValueError("Parameter 'url' is missing")
        response = await open_in_browser(url)
    if name == "execute_sql_query":
        dbname = arguments["dbname"]
        if dbname == None:
            ValueError("Parameter 'dbname' is missing")
        query = arguments["query"]
        if query == None:
            ValueError("Parameter 'query' is missing")
        response = await execute_sql_query(dbname, query)
    if name == "http_get_request":
        url = arguments["url"]
        if url == None:
            ValueError("Parameter 'url' is missing")
        response = await http_get_request(url, arguments["headers"])
    if name == "run_maven_tests":
        test_pattern = arguments["test_pattern"]
        if test_pattern == None:
            ValueError("Parameter 'test_pattern' is missing")
        response = await run_tests("mvn", test_pattern)
    if name == "run_gradle_tests":
        test_pattern = arguments["test_pattern"]
        if test_pattern == None:
            ValueError("Parameter 'test_pattern' is missing")
        response = await run_tests("gradlew", test_pattern)

    return to_text_context(response)        

async def execute_sql_query(dbname: str, query: str) -> str:
    """Executes a read-only SQL query on a database and returns the result as JSON.
    Supports both PostgreSQL and SQL Server databases.
    """
    logger.info(f"Executing SQL query: {query}")

    conn = None
    try:
        async with db_connection_context(dbname, config) as conn:
            logger.info("Database connection established.")
            
            # Determine database vendor
            vendor = config["database"][dbname].get("vendor", "postgresql").lower()
            
            if vendor == "postgresql":
                # PostgreSQL execution
                result = await conn.fetch(query)
                logger.info(f"Query executed successfully on PostgreSQL. Fetched {len(result)} records.")
                result_dict = [dict(record) for record in result]
                
            elif vendor == "sqlserver":
                # SQL Server execution
                cursor = await conn.cursor()
                await cursor.execute(query)
                columns = [column[0] for column in cursor.description]
                rows = await cursor.fetchall()
                await cursor.close()
                
                logger.info(f"Query executed successfully on SQL Server. Fetched {len(rows)} records.")
                result_dict = [dict(zip(columns, row)) for row in rows]
                
            else:
                return json.dumps({"error": f"Unsupported database vendor: {vendor}"})
                
            logger.debug(f"Result of query {query}: {result_dict}")
            return json.dumps(result_dict, cls=CustomJSONEncoder)
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


async def http_get_request(url: str, headers: dict = None) -> str:
    """Makes an HTTP GET request to the specified URL with optional headers.
    This is a read-only operation that retrieves data from a web service.

    Args:
        url (str): The URL to send the GET request to.
        headers (dict, optional): Dictionary of HTTP headers to include. Defaults to None.

    Returns:
        str: A JSON string containing the response status, headers, and body, or an error message.
    """
    logger.info(f"Making GET request to: {url}")
    if url.startswith("http://"):
        logger.error(f"Invalid URL: {url}. URL must start with 'https://'.")
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
        logger.error(f"Unexpected error in http_get_request: {e}", exc_info=True)
        return json.dumps({"error": f"Unexpected server error: {str(e)}"})


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
                    text = html_to_markdown(response.content)
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


async def open_in_browser(url: str) -> str:
    """Opens a url or file in the local browser
    """
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
        # Popen returns immediatly after executing commnad
        subprocess.Popen(
            [browser_command, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True
        )
        return "Browser successfully opened"
    except Exception as e:
        logger.error(f"Error opening url in browser: {e}", exc_info=True)
        return f"Error: {str(e)}"
    
async def run_gradle_tests(test_pattern: str) -> str:
    """Runs Gradle tests. 
    Executes "gradlew test --tests <test_pattern>" in the workspace directory.
    If no test pattern is provided, it runs all tests.

    Args:
        test_pattern (str): The pattern matching test files to execute.

    Returns:
        str: The output of the Gradle test execution.
    """
    return await run_tests("gradlew", test_pattern)


async def run_maven_tests(test_pattern: str) -> str:
    """Runs Maven tests.

    Args:
        test_pattern (str): The pattern matching test files to execute.

    Returns:
        str: The output of the Maven test execution.
    """
    return await run_tests("mvn", test_pattern)

async def run_tests(tool_name: str, test_pattern: str):
    workspace_path = await get_project_folder(server, config)
    if not workspace_path:
        logger.error("Workspace path is not set in the configuration.")
        return "Error: Workspace path is not set in the configuration."

    try:
        if not test_pattern:
            test_pattern = "*"
        if tool_name == "mvn":
            # remove old test results using python file operetions
            test_results_path = os.path.join(workspace_path, "target", "surefire-reports")
            shutil.rmtree(test_results_path)
            # Maven command (with "quit" option)
            test_command = [tool_name, "test", "-q", f"-Dtest={test_pattern}", "surefire-report:report"]
        else:
            # Gradle command, make sure report generation is configured in build.gradle
            test_command = [tool_name, "test", "--tests", test_pattern]

        logger.debug(f"Running test command: {' '.join(test_command)} in {workspace_path}")
        # Execute the command in the workspace directory
        result = subprocess.run(
            test_command,
            cwd=workspace_path,
            text=True,
            capture_output=True,
        )

        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"Tests executed successfully: {result.stdout}")
            return result.stdout
        else:
            errmsg = result.stdout + "\n" + result.stderr
            logger.error(f"Tests failed: {errmsg}")
            return f"Error: {errmsg}"
    except Exception as e:
        logger.error(f"Error running tests: {e}", exc_info=True)
        return f"Error: {str(e)}"

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

async def cleanup():
    """Cleanup resources when the server stops."""
    await close_db_pool()
    await close_http_client()
    logger.info("Cleanup completed.")

if __name__ == "__main__":
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
