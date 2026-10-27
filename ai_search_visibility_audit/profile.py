"""Load and validate generation inputs from JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .fetching import normalize_base_url
from .models import FAQ, PageLink, SiteProfile


class ProfileError(ValueError):
    """Raised when a profile cannot be used safely."""


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{key} must be a non-empty string")
    if len(value.strip()) > 500:
        raise ProfileError(f"{key} is too long")
    return value.strip()


def _text_list(data: dict[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ProfileError(f"{key} must be a list of non-empty strings")
    items = tuple(item.strip() for item in value)
    if required and not items:
        raise ProfileError(f"{key} must contain at least one item")
    if len(items) > 50:
        raise ProfileError(f"{key} contains too many items")
    return items


def _page_url(base_url: str, path: str) -> str:
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        if not path.startswith(base_url.rstrip("/") + "/") and path.rstrip("/") != base_url.rstrip("/"):
            raise ProfileError("page paths must stay on the configured site")
        return path
    if not path.startswith("/"):
        raise ProfileError("page paths must be root-relative")
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def profile_from_dict(data: object) -> SiteProfile:
    if not isinstance(data, dict):
        raise ProfileError("Profile must be a JSON object")
    brand = _required_text(data, "brand")
    tagline = _required_text(data, "tagline")
    audience = _required_text(data, "audience")
    try:
        url = normalize_base_url(_required_text(data, "url"))
    except ValueError as exc:
        raise ProfileError(str(exc)) from exc
    services = _text_list(data, "services", required=True)
    ignore_paths = _text_list(data, "ignore_paths") or (
        "/admin",
        "/dashboard",
        "/login",
        "/checkout",
        "/cart",
    )
    if any(not path.startswith("/") for path in ignore_paths):
        raise ProfileError("ignore_paths entries must be root-relative")

    pages_value = data.get("pages", [])
    if not isinstance(pages_value, list):
        raise ProfileError("pages must be a list")
    pages: list[PageLink] = []
    for index, raw_page in enumerate(pages_value):
        if not isinstance(raw_page, dict):
            raise ProfileError(f"pages[{index}] must be an object")
        title = _required_text(raw_page, "title")
        description = _required_text(raw_page, "description")
        path = _required_text(raw_page, "path")
        _page_url(url, path)
        pages.append(PageLink(title=title, path=path, description=description))
    if len(pages) > 50:
        raise ProfileError("pages contains too many items")

    faq_value = data.get("faqs", [])
    if not isinstance(faq_value, list):
        raise ProfileError("faqs must be a list")
    faqs: list[FAQ] = []
    for index, raw_faq in enumerate(faq_value):
        if not isinstance(raw_faq, dict):
            raise ProfileError(f"faqs[{index}] must be an object")
        faqs.append(
            FAQ(
                question=_required_text(raw_faq, "question"),
                answer=_required_text(raw_faq, "answer"),
            )
        )
    if len(faqs) > 50:
        raise ProfileError("faqs contains too many items")

    return SiteProfile(
        brand=brand,
        tagline=tagline,
        url=url,
        audience=audience,
        services=services,
        pages=tuple(pages),
        ignore_paths=ignore_paths,
        faqs=tuple(faqs),
    )


def load_profile(path: Path) -> SiteProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"Could not read profile: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Profile is not valid JSON: {exc}") from exc
    return profile_from_dict(data)


def absolute_page_url(profile: SiteProfile, page: PageLink) -> str:
    return _page_url(profile.url, page.path)

