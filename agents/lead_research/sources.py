import asyncio
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from agents.lead_research.models import SourcePage

MAX_BYTES = 512_000
USER_AGENT = "ADKAssignmentResearch/0.1"


class SourceError(ValueError):
    """A source cannot be safely or reliably retrieved."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def validate_url(url: str) -> tuple[str, str]:
    if len(url) > 2048 or any(ord(char) < 33 for char in url) or "\\" in url:
        raise SourceError("Invalid URL characters or length")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise SourceError("Only credential-free HTTPS on port 443 is permitted")
    host = parsed.hostname.encode("idna").decode("ascii")
    if host.endswith(".") or host in {"localhost", "metadata.google.internal"}:
        raise SourceError("Internal or ambiguous host")
    return host, (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")


def require_public(addresses: list[str]) -> None:
    if not addresses or any(
        (not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast)
        for address in addresses
    ):
        raise SourceError("DNS resolved to a non-public address")


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self) -> None:
        addresses = list(
            dict.fromkeys(
                str(result[4][0])
                for result in socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
            )
        )
        require_public(addresses)
        # Connect to the validated IP directly; preserve the hostname for TLS verification.
        raw = socket.create_connection((addresses[0], 443), timeout=8)
        try:
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def retrieve(url: str) -> tuple[str, int, str, bytes]:
    original_host, _ = validate_url(url)
    for _ in range(4):
        host, path = validate_url(url)
        if host != original_host:
            raise SourceError("Cross-origin redirect requires separate robots verification")
        connection = PinnedHTTPS(host, timeout=8)
        try:
            connection.request(
                "GET", path, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"}
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise SourceError("Redirect has no Location")
                url = urljoin(url, location)
                continue
            chunks = bytearray()
            deadline = time.monotonic() + 20
            while len(chunks) <= MAX_BYTES:
                if time.monotonic() > deadline:
                    raise SourceError("Source body exceeded time budget")
                chunk = response.read1(min(16384, MAX_BYTES + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            body = bytes(chunks)
            if len(body) > MAX_BYTES:
                raise SourceError("Source exceeds size limit")
            return url, response.status, response.getheader("Content-Type", ""), body
        except (OSError, http.client.HTTPException) as exc:
            raise SourceError("Source network or TLS failure", retryable=True) from exc
        finally:
            connection.close()
    raise SourceError("Too many redirects")


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = 0
        self.in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)
                if self.in_title:
                    self.title.append(cleaned)


class SourceAdapter(Protocol):
    async def fetch(self, url: str) -> SourcePage: ...


class PublicWebsiteSource:
    def _fetch(self, url: str) -> SourcePage:
        host, _ = validate_url(url)
        robots_url, status, _, robots_body = retrieve(f"https://{host}/robots.txt")
        if urlsplit(robots_url).hostname != host:
            raise SourceError("Cross-origin robots redirect requires manual review")
        if status == 200:
            rules = RobotFileParser()
            rules.parse(robots_body.decode("utf-8", errors="replace").splitlines())
            if not rules.can_fetch(USER_AGENT, url):
                raise SourceError("robots.txt disallows retrieval")
            delay = rules.crawl_delay(USER_AGENT)
            if delay and int(delay) > 1:
                raise SourceError("Site requires a longer crawl delay; manual review needed")
        elif status != 404:
            raise SourceError(
                "robots.txt cannot be verified", retryable=status in {429, 502, 503, 504}
            )
        final_url, status, content_type, body = retrieve(url)
        if urlsplit(final_url).hostname != host:
            raise SourceError("Cross-origin page redirect requires a separate robots check")
        if status != 200:
            raise SourceError(
                f"Source HTTP status {status}", retryable=status in {429, 502, 503, 504}
            )
        if not any(mime in content_type.lower() for mime in ("text/html", "text/plain")):
            raise SourceError("Unsupported source content type")
        parser = VisibleText()
        parser.feed(body.decode("utf-8", errors="replace"))
        return SourcePage(
            url=final_url,
            retrieved_at=datetime.now(UTC),
            title=" ".join(parser.title)[:300],
            text="\n".join(parser.parts)[:16000],
            content_sha256=hashlib.sha256(body).hexdigest(),
        )

    async def fetch(self, url: str) -> SourcePage:
        async with asyncio.timeout(60):
            for attempt in range(3):
                try:
                    return await asyncio.to_thread(self._fetch, url)
                except SourceError as exc:
                    if not exc.retryable or attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
        raise SourceError("Source retry budget exhausted")
