from contextlib import asynccontextmanager
from typing import AsyncIterator

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import datetime

# from fake_database import Database  # Replace with your actual DB type

from mcp.server import Server


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
            name="get_local_time",
            description="Get the current local time",
            inputSchema={
                "type": "object",
                "required": []
            }
        )
    ]

@server.call_tool()
async def get_local_time(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Gets the current local time."""
    ctx = server.request_context
    # logger.info("get_local_time called")
    return [types.TextContent(type="text", text=str(datetime.datetime.now()))]

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

    asyncio.run(run())
