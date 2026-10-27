import json
import re
from datetime import date

import pytest

from ai_search_visibility_audit.generate import (
    generate_llms_txt,
    generate_schema_graph,
    render_schema_html,
    write_assets,
)
from ai_search_visibility_audit.profile import ProfileError, profile_from_dict


def profile_data():
    return {
        "brand": "Northwind Dental",
        "tagline": "Practical dental care",
        "url": "https://northwind-dental.example",
        "audience": "Harbor City families",
        "services": ["Preventive care", "Restorative dentistry"],
        "pages": [
            {"title": "About", "path": "/about", "description": "Team and care philosophy"}
        ],
        "ignore_paths": ["/admin"],
        "faqs": [
            {"question": "What care is available?", "answer": "Preventive and restorative care."}
        ],
    }


def test_llms_txt_is_deterministic_and_uses_same_origin_pages():
    profile = profile_from_dict(profile_data())
    output = generate_llms_txt(profile, generated_on=date(2026, 1, 2))
    assert "Last updated: 2026-01-02" in output
    assert "https://northwind-dental.example/about" in output
    assert "## Services" in output


def test_schema_is_a_connected_graph():
    graph = generate_schema_graph(profile_from_dict(profile_data()))
    nodes = graph["@graph"]
    types = [node["@type"] for node in nodes]
    assert types == ["Organization", "WebSite", "Service", "Service", "FAQPage"]
    assert nodes[1]["publisher"]["@id"] == nodes[0]["@id"]
    assert nodes[2]["provider"]["@id"] == nodes[0]["@id"]


def test_schema_script_escapes_html_closing_sequence():
    data = profile_data()
    data["faqs"][0]["answer"] = "Never emit </script> from user-supplied text."
    rendered = render_schema_html(profile_from_dict(data))
    assert rendered.count("</script>") == 1
    assert "<\\/script>" in rendered
    payload = re.search(r"<script[^>]*>\n(.*)\n</script>", rendered, re.DOTALL).group(1)
    assert json.loads(payload)["@graph"][-1]["@type"] == "FAQPage"


def test_profile_refuses_cross_origin_page():
    data = profile_data()
    data["pages"][0]["path"] = "https://other.example/about"
    with pytest.raises(ProfileError, match="configured site"):
        profile_from_dict(data)


def test_write_assets_creates_both_files(tmp_path):
    paths = write_assets(
        profile_from_dict(profile_data()),
        tmp_path,
        generated_on=date(2026, 1, 2),
    )
    assert [path.name for path in paths] == ["llms.txt", "schema.html"]
    assert all(path.is_file() for path in paths)

