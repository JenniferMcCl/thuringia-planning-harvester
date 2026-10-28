"""Local fixture input and an injectable, bounded HTTP acquisition primitive."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .parser import ParsedPage, parse_page


class FetchError(RuntimeError):
    """No successful source observation was obtained."""


def read_fixture(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class HttpFetcher:
    """Future-adapter primitive; does not establish source rights or a live DOM."""

    def __init__(
        self,
        timeout: float = 20,
        retries: int = 2,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.timeout = timeout
        self.retries = retries
        self.session = session if session is not None else requests.Session()
        self.sleep = sleep

    def fetch(self, url: str) -> str:
        host = urlsplit(url).hostname or ""
        if host.endswith(".invalid") or host == "invalid":
            raise FetchError(
                "Reserved fixture hosts must never receive real HTTP requests"
            )
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    headers={"User-Agent": "ThuringiaPlanningPrototype/0.1"},
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt == self.retries:
                    raise FetchError("HTTP connection/timeout failure") from None
            except requests.RequestException:
                raise FetchError("HTTP request failed") from None
            else:
                status = response.status_code
                if status in {401, 403, 429}:
                    raise FetchError(
                        f"HTTP {status}: stop; no access or rate-limit bypass"
                    )
                if status == 200:
                    content_type = (
                        response.headers.get("Content-Type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        raise FetchError("Expected an HTML response from source")
                    if not response.text.strip():
                        raise FetchError("Empty HTTP response")
                    return response.text
                if status < 500 or attempt == self.retries:
                    raise FetchError(f"HTTP {status}: acquisition failed")
            self.sleep(min(2**attempt, 5))
        raise FetchError("Retry limit exhausted")


def fetch_pages(
    first_url: str,
    fetch: Callable[[str], str],
    max_pages: int = 20,
) -> Iterator[ParsedPage]:
    """Callers must collect all pages before persisting a successful batch."""
    url = first_url
    seen = set()
    origin = urlsplit(url).netloc
    for _ in range(max_pages):
        if url in seen:
            raise FetchError("Pagination cycle")
        if urlsplit(url).netloc != origin:
            raise FetchError("Pagination changed origin")
        seen.add(url)
        page = parse_page(fetch(url), url)
        yield page
        if not page.next_url:
            return
        url = page.next_url
    raise FetchError("Pagination exceeded configured page limit")
