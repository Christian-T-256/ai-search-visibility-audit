"""Command-line interface for audits and asset generation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .audit import audit_site
from .fetching import DirectorySiteFetcher, FetchError, SafeHttpFetcher, normalize_base_url
from .generate import write_assets
from .profile import ProfileError, load_profile, profile_from_dict
from .reporting import render_report


DEMO_URL = "https://northwind-dental.example"
DEMO_DATE = date(2026, 10, 26)
DEMO_PROFILE = {
    "brand": "Northwind Dental",
    "tagline": "Clear, practical dental care for Harbor City families",
    "url": DEMO_URL,
    "audience": "Families and adults seeking local dental care",
    "services": ["Preventive dental care", "Restorative dentistry"],
    "pages": [
        {"title": "Home", "path": "/", "description": "Overview of the practice and its approach"},
        {"title": "About", "path": "/about", "description": "Care philosophy and team credentials"},
        {"title": "Services", "path": "/services", "description": "Preventive and restorative services"},
    ],
    "ignore_paths": ["/admin", "/account", "/forms/private"],
    "faqs": [
        {
            "question": "What services does Northwind Dental provide?",
            "answer": "Northwind Dental provides preventive dental care and restorative dentistry for adults and families.",
        },
        {
            "question": "How can a new patient prepare for a first visit?",
            "answer": "Bring a current medication list and any recent dental records, then arrive early to complete the intake form.",
        },
    ],
}


def _print_assets(paths: tuple[Path, Path]) -> None:
    print("\nGenerated assets:")
    for path in paths:
        print(f"  {path}")


def run_demo(output_dir: Path) -> int:
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "northwind-dental"
    fetcher = DirectorySiteFetcher(fixture_dir, DEMO_URL)
    result = audit_site(DEMO_URL, fetcher)
    profile = profile_from_dict(DEMO_PROFILE)
    assets = write_assets(profile, output_dir, generated_on=DEMO_DATE)
    print("Offline demo: all site responses came from packaged fixture files")
    print(render_report(result), end="")
    _print_assets(assets)
    return 0


def run_audit(url: str, as_json: bool) -> int:
    result = audit_site(url, SafeHttpFetcher())
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(render_report(result), end="")
    return 0


def run_generate(config: Path, output_dir: Path) -> int:
    profile = load_profile(config)
    assets = write_assets(profile, output_dir)
    _print_assets(assets)
    return 0


def run_full(url: str, config: Path, output_dir: Path, as_json: bool) -> int:
    profile = load_profile(config)
    normalized_url = normalize_base_url(url)
    if normalized_url != profile.url:
        raise ProfileError("The audit URL must exactly match the URL in the generation profile")
    result = audit_site(normalized_url, SafeHttpFetcher())
    assets = write_assets(profile, output_dir)
    if as_json:
        payload = result.to_dict()
        payload["generated_assets"] = [str(path) for path in assets]
        print(json.dumps(payload, indent=2))
    else:
        print(render_report(result), end="")
        _print_assets(assets)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-search-visibility-audit",
        description="Audit technical AI search visibility and generate remediation assets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the complete offline fictional demo")
    demo.add_argument("--output-dir", type=Path, default=Path("output/demo"))

    audit = subparsers.add_parser("audit", help="Audit a public website")
    audit.add_argument("url")
    audit.add_argument("--json", action="store_true", dest="as_json")

    generate = subparsers.add_parser("generate", help="Generate llms.txt and JSON-LD from a profile")
    generate.add_argument("--config", type=Path, required=True)
    generate.add_argument("--output-dir", type=Path, default=Path("output/site"))

    full = subparsers.add_parser("run", help="Audit a public site and generate its assets")
    full.add_argument("url")
    full.add_argument("--config", type=Path, required=True)
    full.add_argument("--output-dir", type=Path, default=Path("output/site"))
    full.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            return run_demo(args.output_dir)
        if args.command == "audit":
            return run_audit(args.url, args.as_json)
        if args.command == "generate":
            return run_generate(args.config, args.output_dir)
        if args.command == "run":
            return run_full(args.url, args.config, args.output_dir, args.as_json)
    except (FetchError, ProfileError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
