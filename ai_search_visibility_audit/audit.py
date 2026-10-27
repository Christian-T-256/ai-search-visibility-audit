"""Deterministic scoring for AI answer-engine discoverability signals."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

from .fetching import FetchError, SiteFetcher, normalize_base_url, origin, site_url
from .models import AuditResult, SignalResult


SIGNALS: tuple[tuple[str, int, str], ...] = (
    ("llms_txt", 12, "llms.txt file present"),
    ("org_schema", 10, "Organization JSON-LD schema"),
    ("faq_schema", 10, "FAQPage JSON-LD schema"),
    ("service_schema", 8, "Service or Product JSON-LD schema"),
    ("article_schema", 5, "Article or BlogPosting JSON-LD schema"),
    ("meta_description", 6, "Meta description present"),
    ("og_tags", 5, "Open Graph title and description"),
    ("h1_present", 5, "Exactly one H1"),
    ("faq_content", 8, "Visible FAQ content"),
    ("direct_answer_para", 7, "Direct answer paragraph near page start"),
    ("sitemap", 5, "XML sitemap present"),
    ("robots_txt", 4, "robots.txt allows major AI crawlers"),
    ("author_info", 5, "About or team page present"),
    ("https", 5, "HTTPS enabled"),
    ("canonical", 5, "Canonical URL tag"),
)

AI_BOTS = ("GPTBot", "PerplexityBot", "ClaudeBot", "Google-Extended", "Bytespider", "CCBot")

FIXES = {
    "llms_txt": "Publish the generated llms.txt at /llms.txt.",
    "org_schema": "Add Organization JSON-LD with a stable @id.",
    "faq_schema": "Add FAQPage JSON-LD that matches visible questions and answers.",
    "service_schema": "Describe each offering with Service or Product JSON-LD.",
    "article_schema": "Add Article or BlogPosting JSON-LD on editorial pages.",
    "meta_description": "Add a concise meta description that states the page purpose.",
    "og_tags": "Add og:title and og:description metadata.",
    "h1_present": "Use exactly one descriptive H1 on the page.",
    "faq_content": "Publish visible question and answer content in the HTML.",
    "direct_answer_para": "Put a self-contained 30 to 150 word answer near the top.",
    "sitemap": "Publish an XML sitemap at /sitemap.xml.",
    "robots_txt": "Publish robots.txt and allow the listed AI crawlers to fetch the homepage.",
    "author_info": "Publish an /about or /team page with relevant credentials.",
    "https": "Serve the public site over HTTPS.",
    "canonical": "Add a canonical link that points to the preferred page URL.",
}


class PageParser(HTMLParser):
    """Extract only the small set of HTML facts needed by the audit."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_description = ""
        self.open_graph: dict[str, str] = {}
        self.h1_count = 0
        self.canonical = ""
        self.json_ld: list[object] = []
        self.paragraphs: list[str] = []
        self.visible_text: list[str] = []
        self._json_ld_depth = 0
        self._json_ld_text: list[str] = []
        self._paragraph_depth = 0
        self._paragraph_text: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag in {"script", "style", "template", "noscript"}:
            if tag == "script" and values.get("type", "").lower() == "application/ld+json":
                self._json_ld_depth = 1
                self._json_ld_text = []
            else:
                self._hidden_depth += 1
            return
        if self._json_ld_depth:
            self._json_ld_depth += 1
        if tag == "meta":
            name = values.get("name", "").lower()
            prop = values.get("property", "").lower()
            if name == "description":
                self.meta_description = values.get("content", "").strip()
            if prop.startswith("og:"):
                self.open_graph[prop] = values.get("content", "").strip()
        elif tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonical = values.get("href", "").strip()
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "p" and not self._hidden_depth:
            self._paragraph_depth += 1
            if self._paragraph_depth == 1:
                self._paragraph_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._json_ld_depth:
            self._json_ld_depth -= 1
            if tag == "script" and self._json_ld_depth == 0:
                try:
                    self.json_ld.append(json.loads("".join(self._json_ld_text)))
                except json.JSONDecodeError:
                    pass
            return
        if tag in {"script", "style", "template", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1
            return
        if tag == "p" and self._paragraph_depth:
            self._paragraph_depth -= 1
            if self._paragraph_depth == 0:
                paragraph = " ".join(self._paragraph_text).strip()
                if paragraph:
                    self.paragraphs.append(paragraph)

    def handle_data(self, data: str) -> None:
        if self._json_ld_depth:
            self._json_ld_text.append(data)
            return
        if self._hidden_depth:
            return
        clean = " ".join(data.split())
        if clean:
            self.visible_text.append(clean)
            if self._paragraph_depth:
                self._paragraph_text.append(clean)


def extract_schema_types(value: object) -> set[str]:
    """Recursively find @type values, including arrays and @graph nodes."""
    found: set[str] = set()
    if isinstance(value, dict):
        schema_type = value.get("@type")
        if isinstance(schema_type, str):
            found.add(schema_type)
        elif isinstance(schema_type, list):
            found.update(item for item in schema_type if isinstance(item, str))
        for child in value.values():
            if isinstance(child, (dict, list)):
                found.update(extract_schema_types(child))
    elif isinstance(value, list):
        for child in value:
            found.update(extract_schema_types(child))
    return found


def _has_direct_answer(paragraphs: list[str]) -> bool:
    words_seen = 0
    for paragraph in paragraphs:
        count = len(paragraph.split())
        if words_seen >= 150:
            break
        if 30 <= count <= 150:
            return True
        words_seen += count
    return False


def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def audit_site(base_url: str, fetcher: SiteFetcher) -> AuditResult:
    """Audit one homepage and its root-level discovery files."""
    base_url = normalize_base_url(base_url)
    homepage = fetcher.fetch(base_url + "/")
    if not homepage.ok or not homepage.text.strip():
        raise FetchError(f"Homepage returned status {homepage.status}")

    parser = PageParser()
    parser.feed(homepage.text)
    schema_types: set[str] = set()
    for block in parser.json_ld:
        schema_types.update(extract_schema_types(block))

    llms = fetcher.fetch(site_url(base_url, "/llms.txt"))
    sitemap = fetcher.fetch(site_url(base_url, "/sitemap.xml"))
    robots_url = site_url(base_url, "/robots.txt")
    robots = fetcher.fetch(robots_url)
    about = fetcher.fetch(site_url(base_url, "/about"))
    team = fetcher.fetch(site_url(base_url, "/team"))

    blocked_bots: list[str] = []
    if robots.ok and robots.text.strip():
        robot_parser = RobotFileParser()
        robot_parser.set_url(robots_url)
        robot_parser.parse(robots.text.splitlines())
        homepage_url = origin(base_url) + "/"
        blocked_bots = [bot for bot in AI_BOTS if not robot_parser.can_fetch(bot, homepage_url)]

    visible = " ".join(parser.visible_text[:200]).lower()
    has_faq = bool(re.search(r"\b(faq|frequently asked|common questions|questions and answers)\b", visible))
    org_types = {"Organization", "LocalBusiness", "Corporation", "Brand"}
    service_types = {"Service", "Product", "Offer", "SoftwareApplication", "ProfessionalService"}
    article_types = {"Article", "BlogPosting", "NewsArticle"}

    checks: dict[str, tuple[bool, str]] = {
        "llms_txt": (llms.ok and bool(llms.text.strip()), "Found /llms.txt" if llms.ok and llms.text.strip() else "No /llms.txt response was found"),
        "org_schema": (bool(schema_types & org_types), f"Found {', '.join(sorted(schema_types & org_types))}" if schema_types & org_types else "No organization entity was found"),
        "faq_schema": ("FAQPage" in schema_types, "Found FAQPage" if "FAQPage" in schema_types else "No FAQPage entity was found"),
        "service_schema": (bool(schema_types & service_types), f"Found {', '.join(sorted(schema_types & service_types))}" if schema_types & service_types else "No service or product entity was found"),
        "article_schema": (bool(schema_types & article_types), f"Found {', '.join(sorted(schema_types & article_types))}" if schema_types & article_types else "No article entity was found"),
        "meta_description": (bool(parser.meta_description), "Meta description is present" if parser.meta_description else "Meta description is missing"),
        "og_tags": ({"og:title", "og:description"} <= parser.open_graph.keys(), "Open Graph title and description are present" if {"og:title", "og:description"} <= parser.open_graph.keys() else "Open Graph title or description is missing"),
        "h1_present": (parser.h1_count == 1, "Found exactly one H1" if parser.h1_count == 1 else f"Found {parser.h1_count} H1 elements"),
        "faq_content": (has_faq, "FAQ language is visible in the page HTML" if has_faq else "No visible FAQ section was detected"),
        "direct_answer_para": (_has_direct_answer(parser.paragraphs), "A 30 to 150 word paragraph appears near the top" if _has_direct_answer(parser.paragraphs) else "No 30 to 150 word paragraph appears in the first 150 words"),
        "sitemap": (sitemap.ok and bool(sitemap.text.strip()), "Found /sitemap.xml" if sitemap.ok and sitemap.text.strip() else "No /sitemap.xml response was found"),
        "robots_txt": (robots.ok and bool(robots.text.strip()) and not blocked_bots, "robots.txt allows the audited AI crawlers" if robots.ok and robots.text.strip() and not blocked_bots else (f"robots.txt blocks: {', '.join(blocked_bots)}" if blocked_bots else "No robots.txt response was found")),
        "author_info": (about.ok or team.ok, "Found an about or team page" if about.ok or team.ok else "No /about or /team page was found"),
        "https": (base_url.startswith("https://"), "The site uses HTTPS" if base_url.startswith("https://") else "The site uses HTTP"),
        "canonical": (bool(parser.canonical), f"Canonical points to {parser.canonical}" if parser.canonical else "Canonical link is missing"),
    }

    signal_results = tuple(
        SignalResult(
            key=key,
            label=label,
            weight=weight,
            passed=checks[key][0],
            evidence=checks[key][1],
            fix=None if checks[key][0] else FIXES[key],
        )
        for key, weight, label in SIGNALS
    )
    total = sum(signal.weight for signal in signal_results)
    earned = sum(signal.weight for signal in signal_results if signal.passed)
    score = round(earned / total * 100)
    return AuditResult(
        url=base_url,
        score=score,
        grade=_grade(score),
        earned_points=earned,
        total_points=total,
        schema_types=tuple(sorted(schema_types)),
        signals=signal_results,
    )

