import json

from ai_search_visibility_audit.cli import main


def test_demo_runs_offline_and_writes_assets(tmp_path, capsys):
    exit_code = main(["demo", "--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Score: 37/100 (Grade F)" in captured.out
    assert "Prioritized fixes:" in captured.out
    assert (tmp_path / "llms.txt").is_file()
    assert (tmp_path / "schema.html").is_file()


def test_run_refuses_mismatched_audit_and_profile_urls(tmp_path, capsys):
    config = tmp_path / "profile.json"
    config.write_text(
        json.dumps(
            {
                "brand": "Northwind Dental",
                "tagline": "Practical dental care",
                "url": "https://northwind-dental.example",
                "audience": "Harbor City families",
                "services": ["Preventive care"],
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run",
            "https://other.example",
            "--config",
            str(config),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
    assert "exactly match" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()

