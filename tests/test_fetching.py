import socket
from pathlib import Path

import pytest

from ai_search_visibility_audit.fetching import (
    DirectorySiteFetcher,
    FetchError,
    normalize_base_url,
    validate_public_url,
)


FIXTURES = Path(__file__).resolve().parents[1] / "ai_search_visibility_audit" / "fixtures"
URL = "https://northwind-dental.example"


def test_directory_fetcher_maps_routes_without_network():
    fetcher = DirectorySiteFetcher(FIXTURES / "northwind-dental", URL)
    assert fetcher.fetch(URL + "/").status == 200
    assert fetcher.fetch(URL + "/about").status == 200
    assert fetcher.fetch(URL + "/missing").status == 404
    assert fetcher.fetch("https://other.example/").status == 404


def test_directory_fetcher_rejects_traversal():
    fetcher = DirectorySiteFetcher(FIXTURES / "northwind-dental", URL)
    assert fetcher.fetch(URL + "/%2e%2e/config.example.json").status == 404


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/site",
        "https://user:pass@example.com",
        "https://example.com:8080",
        "https://example.com/?next=other",
    ],
)
def test_url_normalization_rejects_unsafe_shapes(url):
    with pytest.raises(ValueError):
        normalize_base_url(url)


def test_public_url_check_blocks_private_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(FetchError, match="Private"):
        validate_public_url("https://internal.example/path")
