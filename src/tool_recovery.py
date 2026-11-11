"""Small bounded retry policy for Tavily operations; never logs request contents."""
import logging
import builtins
import time
from requests.exceptions import Timeout, ConnectionError
from tavily.errors import TimeoutError as TavilyTimeoutError

logger = logging.getLogger(__name__)


def transient_tool_error(error):
    if isinstance(error, PermissionError):
        return False
    status = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)
    if status in (400, 401, 403, 404):
        return False
    return isinstance(error, (TimeoutError, Timeout, ConnectionError, builtins.ConnectionError, TavilyTimeoutError)) or status in (408, 429, 500, 502, 503, 504)


def call_tavily(operation, *args, max_retries=1, **kwargs):
    for attempt in range(max_retries + 1):
        try:
            return operation(*args, **kwargs)
        except Exception as error:
            if attempt == max_retries or not transient_tool_error(error):
                raise
            delay = 0.5 * (2 ** attempt)
            logger.warning('Tavily transient failure exception=%s retry=%d delay=%.1f', type(error).__name__, attempt + 1, delay)
            time.sleep(delay)
