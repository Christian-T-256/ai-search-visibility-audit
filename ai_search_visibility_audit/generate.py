"""Generate llms.txt and connected JSON-LD from a validated profile."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable

from .models import SiteProfile
from .profile import absolute_page_url


def generate_llms_txt(profile: SiteProfile, generated_on: date | None = None) -> str:
    """Render an llms.txt document without crawling or model calls."""
    generated_on = generated_on or date.today()
    lines = [
        f"# {profile.brand}",
        "",
        f"> {profile.tagline}",
        "",
        f"Website: {profile.url}",
        f"Last updated: {generated_on.isoformat()}",
        f"Primary audience: {profile.audience}",
        "",
        "## About",
        "",
        f"{profile.brand} serves {profile.audience.lower()}. Its core offerings are {', '.join(profile.services)}.",
        "",
        "## Key Pages",
        "",
    ]
    pages = profile.pages or ()
    if pages:
        for page in pages:
            lines.append(f"- [{page.title}]({absolute_page_url(profile, page)}): {page.description}")
    else:
        lines.append(f"- [Homepage]({profile.url}/): Overview of {profile.brand} and its services")
    lines.extend(["", "## Services", ""])
    lines.extend(f"- {service}" for service in profile.services)
    lines.extend(
        [
            "",
            "## Site Index",
            "",
            f"- [XML sitemap]({profile.url}/sitemap.xml): Complete list of public pages",
            "",
            "## Optional",
            "",
            "The following paths contain operational pages that are not useful for answering public questions:",
            "",
        ]
    )
    lines.extend(f"- {path}" for path in profile.ignore_paths)
    return "\n".join(lines) + "\n"


def generate_schema_graph(profile: SiteProfile) -> dict[str, object]:
    """Build one connected Schema.org graph with stable entity identifiers."""
    base = profile.url.rstrip("/")
    organization_id = f"{base}/#organization"
    website_id = f"{base}/#website"
    graph: list[dict[str, object]] = [
        {
            "@type": "Organization",
            "@id": organization_id,
            "name": profile.brand,
            "url": f"{base}/",
            "description": profile.tagline,
        },
        {
            "@type": "WebSite",
            "@id": website_id,
            "url": f"{base}/",
            "name": profile.brand,
            "publisher": {"@id": organization_id},
            "audience": {"@type": "Audience", "audienceType": profile.audience},
        },
    ]
    for index, service in enumerate(profile.services, start=1):
        graph.append(
            {
                "@type": "Service",
                "@id": f"{base}/#service-{index}",
                "name": service,
                "url": f"{base}/services",
                "provider": {"@id": organization_id},
                "audience": {"@type": "Audience", "audienceType": profile.audience},
            }
        )
    if profile.faqs:
        graph.append(
            {
                "@type": "FAQPage",
                "@id": f"{base}/#faq",
                "url": f"{base}/#faq",
                "isPartOf": {"@id": website_id},
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": faq.question,
                        "acceptedAnswer": {"@type": "Answer", "text": faq.answer},
                    }
                    for faq in profile.faqs
                ],
            }
        )
    return {"@context": "https://schema.org", "@graph": graph}


def render_schema_html(profile: SiteProfile) -> str:
    """Render JSON-LD as a safe script block for manual head injection."""
    payload = json.dumps(generate_schema_graph(profile), indent=2, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    return (
        '<script type="application/ld+json">\n'
        + payload
        + "\n</script>\n"
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_assets(
    profile: SiteProfile,
    output_dir: Path,
    generated_on: date | None = None,
    writer: Callable[[Path, str], None] = _atomic_write,
) -> tuple[Path, Path]:
    """Write both assets only after rendering both successfully."""
    llms_content = generate_llms_txt(profile, generated_on=generated_on)
    schema_content = render_schema_html(profile)
    llms_path = output_dir / "llms.txt"
    schema_path = output_dir / "schema.html"
    writer(llms_path, llms_content)
    writer(schema_path, schema_content)
    return llms_path, schema_path

