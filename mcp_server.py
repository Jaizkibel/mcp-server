import datetime
import os
import platform  # Add platform module import
from typing import Any
import json
from decimal import Decimal
from mcp.server.fastmcp import FastMCP
import logging
import asyncio
import yaml
import pathspec  # Add pathspec module import
import subprocess

from utils.args import parse_arguments
from utils.db import close_db_pool, db_connection_context
from utils.web import (
    close_http_client,
    http_client_context,
    strip_strong_tags,
    strip_text_from_html,
)
from utils.web import (
    close_http_client,
    http_client_context,
    strip_strong_tags,
    strip_text_from_html,
)
from pathlib import Path

# Configure logging
logging.basicConfig(
    filename="mcp_server.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

configPath = f"{Path.home()}/.mcp-server/config.yml"
config = {}


# Custom JSON encoder to handle Decimal and datetime objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)


# init MCP server
mcp = FastMCP("test")
logger.info("MCP server initialized")


# @mcp.tool()
# async def get_local_time() -> str:
#     """Gets the current local time."""
#     logger.info("get_local_time called")
#     return str(datetime.datetime.now())


@mcp.tool()
async def get_os_info() -> str:
    """Get information about the local operating system.
    This is a read-only operation and does not change any system state.
    Works on all operating systems including Windows, macOS, and Linux.

    Returns:
        str: A JSON string containing detailed OS information.
    """
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


@mcp.tool()
async def ls_workspace() -> str:
    """Lists all files in the current project workspace, excluding those matching .gitignore patterns.

    Returns
        str: The list of workspace files separated by line breaks"""
    workspace_path = config.get("projectFolder")
    if workspace_path is None:
        logger.error("ls_workspace: Workspace path is not set in the configuration")
        return "Error: Workspace path is not set in the configuration"

    try:
        result = []
        non_empty_dirs = set()  # Keep track of non-empty directories

        # Read .gitignore file if it exists
        gitignore_path = os.path.join(workspace_path, ".gitignore")
        if os.path.isfile(gitignore_path):
            try:
                with open(gitignore_path, "r") as f:
                    gitignore_content = f.read()
                # Create pathspec object from gitignore content
                spec = pathspec.PathSpec.from_lines(
                    "gitwildmatch", gitignore_content.splitlines()
                )
                logger.info(f"Loaded .gitignore patterns from {gitignore_path}")
            except Exception as e:
                logger.warning(f"Failed to load .gitignore file: {e}")
                spec = None
        else:
            logger.info("No .gitignore file found")
            spec = None

        # Helper function to check if a path should be ignored, because in gitignore
        def should_ignore(path):
            if spec is None:
                return False
            # Normalize path for cross-platform compatibility
            norm_path = path.replace(os.sep, "/")
            return spec.match_file(norm_path)

        # First pass: collect files and track which directories have files
        for root, _, files in os.walk(workspace_path):
            for file in files:
                # Get the relative path from the workspace root
                rel_path = os.path.relpath(os.path.join(root, file), workspace_path)
                # Skip if it matches .gitignore pattern
                if should_ignore(rel_path):
                    logger.debug(f"Ignoring {rel_path} (matches .gitignore pattern)")
                    continue

                result.append(rel_path)

        files_list = "\n".join(sorted(result))
        logger.info(f"Workspace files: {files_list}")
        return files_list
    except Exception as e:
        logger.error(f"Error listing workspace files: {e}", exc_info=True)
        return str(e)


@mcp.tool()
async def execute_sql_query(query: str) -> str:
    """Executes a read-only SQL query on a PostgreSQL database and returns the result as JSON.
    It connects using a read-only user.
    This tool assumes the query is read-only (e.g., SELECT). It should not be used for data modification (INSERT, UPDATE, DELETE).

    Args:
        query (str): The SQL query to execute (should be read-only).

    Returns:
        str: The result of the query as JSON, or an error message.
    """
    logger.info(f"Executing SQL query: {query}")

    if config["dbName"] is None:
        logger.error("Database name not specified in configuration")
        return json.dumps({"error": "Database name not specified in configuration"})

    conn = None
    try:
        async with db_connection_context(config=config) as conn:
            logger.info("Database connection established.")
            result = await conn.fetch(query)
            logger.info(f"Query executed successfully. Fetched {len(result)} records.")
            result_dict = [dict(record) for record in result]
            logger.debug(f"Result of query {query}: {result_dict}")
            return json.dumps(result_dict, cls=CustomJSONEncoder)
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@mcp.tool()
async def query_web(query: str) -> str:
    """Executes a search query using the Brave Search API and fetches content from the top results.
    This is a read-only operation retrieving information from the web.

    Args:
        query (str): The search query.

    Returns:
        str: A JSON string containing the URLs, descriptions, and fetched content of the found web sites, or an error message.
    """
    logger.info(f"Executing web query: {query}")
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


@mcp.tool()
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


@mcp.tool()
async def http_post_request(url: str, body: dict = None, headers: dict = None) -> str:
    """Makes an HTTP POST request to the specified URL with optional headers and body.
    This operation sends data to a web service.

    Args:
        url (str): The URL to send the POST request to.
        body (dict, optional): Dictionary of data to send in the request body. Defaults to None.
        headers (dict, optional): Dictionary of HTTP headers to include. Defaults to None.

    Returns:
        str: A JSON string containing the response status, headers, and body, or an error message.
    """
    logger.info(f"Making POST request to: {url}")
    try:
        final_headers = headers or {}
        if "Content-Type" not in final_headers and body is not None:
            final_headers["Content-Type"] = "application/json"

        async with http_client_context() as client:
            response = await client.post(url, json=body, headers=final_headers)
            response.raise_for_status()
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
            return json.dumps(result, cls=CustomJSONEncoder)
    except Exception as e:
        logger.error(f"Unexpected error in http_post_request: {e}", exc_info=True)
        return json.dumps({"error": f"Unexpected server error: {str(e)}"})


@mcp.tool()
async def open_in_browser(url: str) -> str:
    """Opens a url or file in the local browser

    Args:
        url (str): The URL or file path to open.

    Returns: a success or error message
    """
    if not url.endswith(".html"):
        return "Error: can open HTML pages only"
    workspace_path = config.get("projectFolder")
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
        command = [browser_command, url]
        # Execute command to open browser
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
        )

        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"result of open_in_browser: {result}")
            return "Browser successfully opened"
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        logger.error(f"Error opening url in browser: {e}", exc_info=True)
        return f"Error: {str(e)}"


@mcp.tool()
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


@mcp.tool()
async def run_maven_tests(test_pattern: str) -> str:
    """Runs Maven tests.

    Args:
        test_pattern (str): The pattern matching test files to execute.

    Returns:
        str: The output of the Maven test execution.
    """
    return await run_tests("mvn", test_pattern)


async def run_tests(tool_name: str, test_pattern: str):
    workspace_path = config.get("projectFolder")
    if not workspace_path:
        logger.error("Workspace path is not set in the configuration.")
        return "Error: Workspace path is not set in the configuration."

    try:
        if not test_pattern:
            test_pattern = "*"
        if tool_name == "mvn":
            # Maven command (with "quit" option)
            test_command = [tool_name, "test", "-q", f"-Dtest={test_pattern}"]
        else:
            # Gradle command
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


def is_relative_path(path: str) -> bool:
    """Check if the given path is relative."""
    if path.startswith("http"):
        return False

    return not os.path.isabs(path)


if __name__ == "__main__":

    async def cleanup():
        """Cleanup resources when the server stops."""
        await close_db_pool()
        await close_http_client()
        logger.info("Cleanup completed.")

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

    # Start the MCP server
    try:
        logger.info("Starting MCP server with stdio transport.")
        mcp.run(transport="stdio")
    finally:
        asyncio.run(cleanup())
        logger.info("MCP server stopped.")
