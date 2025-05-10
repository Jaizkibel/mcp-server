import mcp.types as types
from mcp.server.lowlevel import Server




def to_text_context(text: str) -> list[types.TextContent]: 
    """ convert text to list of TextContent needed as tool call return value"""
    return [types.TextContent(type="text", text=text)]

def get_workspace_capabilities(server: Server) -> dict:
    capabilies = server.get_capabilities

    return capabilies