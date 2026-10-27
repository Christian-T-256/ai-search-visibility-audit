"""Audit and improve a website's technical AI search visibility."""

from .audit import SIGNALS, audit_site, extract_schema_types
from .fetching import DirectorySiteFetcher, FetchError, SafeHttpFetcher
from .generate import generate_llms_txt, generate_schema_graph, render_schema_html, write_assets
from .profile import ProfileError, load_profile, profile_from_dict

__all__ = [
    "SIGNALS",
    "DirectorySiteFetcher",
    "FetchError",
    "ProfileError",
    "SafeHttpFetcher",
    "audit_site",
    "extract_schema_types",
    "generate_llms_txt",
    "generate_schema_graph",
    "load_profile",
    "profile_from_dict",
    "render_schema_html",
    "write_assets",
]

