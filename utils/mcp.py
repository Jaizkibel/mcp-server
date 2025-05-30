import logging
import os
from mcp import ClientCapabilities, ServerSession
import mcp.types as types
from mcp.server.lowlevel import Server


logger = logging.getLogger(__name__)


def to_text_context(text: str) -> list[types.TextContent]: 
    """ convert text to list of TextContent needed as tool call return value"""
    # logger.debug(f"converting text '{text}' to list of TextContent")
    if text is None:
        text = "No text available"
    return [types.TextContent(type="text", text=text)]

async def get_project_folder(server: Server, config: dict) -> str:
    """Gets project directory from config.
    If not set try to ask mcp client for root directory
    """
    config_path = config.get("projectFolder")
    if config_path != None:
        return config_path
    
    session: ServerSession = server.request_context.session
    try:
        caps: ClientCapabilities = session.client_params.capabilities
        logger.debug(f"Client caps: {caps}")
        if caps.roots != None:
            roots = await session.list_roots()
            logger.debug(f"Client roots: {roots}")
            # roots are always of type file (not http),
            # so we don't need to filter
            uri = roots.roots[0].uri
            logger.debug(f"root path: {uri.path}")
            return uri.path
            
    except Exception as e:
        logger.error(f"Failed to list roots: {e}", exc_info=True)
        return None
    
def is_relative_path(path: str) -> bool:
    """Check if the given path is relative."""
    if path.startswith("http"):
        return False

    return not os.path.isabs(path)


