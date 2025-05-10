# Global HTTP client with connection pooling
from contextlib import asynccontextmanager
import datetime
from decimal import Decimal
import json
import logging
from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

_http_client = None

# Custom JSON encoder to handle Decimal and datetime objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)

            
async def get_http_client() -> httpx.AsyncClient:
    """Get or create a shared AsyncClient instance with connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=10.0,
            verify=False  # Disables SSL certificate validation
        )
    return _http_client

@asynccontextmanager
async def http_client_context():
    """Context manager for HTTP client operations."""
    client = await get_http_client()
    try:
        yield client
    except Exception as e:
        logger.error(f"HTTP client error: {e}", exc_info=True)
        raise

def strip_text_from_html(html_content: bytes) -> str:
    """Strips unwanted tags and extracts text from HTML content."""
    try:
        # Specify a parser like 'html.parser' or 'lxml' if installed
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove tags that typically don't contain main content
        tags_to_remove = [
            "script",
            "style",
            "meta",
            "link",
            "head",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button",
            "img",
            "svg",
            "iframe",
            "noscript",
        ]
        for tag in soup.find_all(tags_to_remove):
            tag.decompose()

        # Get text, separated by newlines, and strip leading/trailing whitespace from each line
        text_lines = (
            line.strip() for line in soup.get_text(separator="\n").splitlines()
        )
        # Join lines back, keeping only non-empty lines
        return "\n".join(line for line in text_lines if line)
    except Exception as e:
        logger.error(f"Error stripping HTML: {e}", exc_info=True)
        return "Error processing HTML content" 

def strip_strong_tags(text: str) -> str:
    """Strips <strong> tags from HTML content."""
    if not isinstance(text, str):
        logger.warning(f"Attempted to strip tags from non-string type: {type(text)}")
        return text
    new_text = text.replace("<strong>", "").replace("</strong>", "")
    return new_text

async def close_http_client():
    """Close the shared HTTP client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


