"""Safe live and local transports for the audit engine."""

from __future__ import annotations

import ipaddress
import mimetypes
import socket
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import FetchResponse


MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_PORTS = {80, 443}


class FetchError(RuntimeError):
    """Raised when a site cannot be fetched safely."""


class SiteFetcher(Protocol):
    def fetch(self, url: str) -> FetchResponse:
        """Fetch one URL and return a normalized response."""


def normalize_base_url(url: str) -> str:
    """Validate and normalize a website origin or root URL."""
    candidate = url.strip()
    if not candidate:
        raise ValueError("Website URL cannot be empty")
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Website URL must use http or https")
    if not parsed.hostname:
        raise ValueError("Website URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("Website URL cannot contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Website URL contains an invalid port") from exc
    if port and port not in ALLOWED_PORTS:
        raise ValueError("Website URL must use port 80 or 443")
    if parsed.query or parsed.fragment:
        raise ValueError("Website URL cannot contain a query string or fragment")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_public_url(url: str) -> None:
    """Reject local, private, and unusual network destinations."""
    normalized = normalize_base_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if hostname.lower() == "localhost":
        raise FetchError("Localhost targets are blocked")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve hostname: {hostname}") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise FetchError("Private or non-routable network targets are blocked")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SafeHttpFetcher:
    """Bounded HTTP transport with SSRF and redirect checks."""

    def __init__(self, timeout: float = 10.0, max_bytes: int = MAX_RESPONSE_BYTES):
        if timeout <= 0 or max_bytes <= 0:
            raise ValueError("timeout and max_bytes must be positive")
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._opener = build_opener(_SafeRedirectHandler())

    def fetch(self, url: str) -> FetchResponse:
        validate_public_url(url)
        request = Request(
            url,
            headers={"User-Agent": "AI-Search-Visibility-Audit/1.0"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = response.read(self.max_bytes + 1)
                if len(data) > self.max_bytes:
                    raise FetchError(f"Response exceeded {self.max_bytes} bytes")
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"
                return FetchResponse(
                    url=response.geturl(),
                    status=response.status,
                    text=data.decode(charset, errors="replace"),
                    content_type=content_type,
                )
        except HTTPError as exc:
            return FetchResponse(url=url, status=exc.code, text="")
        except (URLError, TimeoutError, OSError) as exc:
            raise FetchError(f"Could not fetch {url}: {exc.reason if isinstance(exc, URLError) else exc}") from exc


class DirectorySiteFetcher:
    """Serve a public-looking origin from a local fixture directory."""

    def __init__(self, root: Path, base_url: str):
        self.root = root.resolve()
        self.base_url = normalize_base_url(base_url)
        self._origin = origin(self.base_url)
        if not self.root.is_dir():
            raise ValueError(f"Fixture directory does not exist: {root}")

    def _resolve(self, url: str) -> Path | None:
        parsed = urlparse(url)
        if origin(url) != self._origin:
            return None
        decoded = unquote(parsed.path)
        pure = PurePosixPath(decoded)
        if ".." in pure.parts:
            return None
        relative = Path(*[part for part in pure.parts if part not in {"/", ""}])
        candidates = [self.root / relative]
        if not relative.suffix:
            candidates.extend([self.root / f"{relative}.html", self.root / relative / "index.html"])
        if decoded in {"", "/"}:
            candidates.insert(0, self.root / "index.html")
        for candidate in candidates:
            resolved = candidate.resolve()
            if self.root not in resolved.parents and resolved != self.root:
                continue
            if resolved.is_file():
                return resolved
        return None

    def fetch(self, url: str) -> FetchResponse:
        path = self._resolve(url)
        if path is None:
            return FetchResponse(url=url, status=404, text="")
        content_type = mimetypes.guess_type(path.name)[0] or "text/plain"
        return FetchResponse(
            url=url,
            status=200,
            text=path.read_text(encoding="utf-8"),
            content_type=content_type,
        )


def site_url(base_url: str, path: str) -> str:
    """Join a root-relative site path without losing a base path."""
    return urljoin(origin(base_url) + "/", path.lstrip("/"))

