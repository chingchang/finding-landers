"""Publishing a run: sealed names redacted and counted, manifests left behind, numbers untouched."""

import json

from landers.models import publish


def sites_file(tmp_path, monkeypatch):
    p = tmp_path / "sites.json"
    p.write_text(
        json.dumps(
            {
                "sites": [
                    {"name": "alpha", "group": "tuning"},
                    {"name": "bravo2", "group": "heldout"},
                    {"name": "charlie", "group": "final_exam"},
                ]
            }
        )
    )
    monkeypatch.setenv("LEAKCHECK_SITES", str(p))
    return p


def test_sealed_names_come_from_the_sites_file(tmp_path, monkeypatch):
    sites_file(tmp_path, monkeypatch)
    assert publish.sealed_names() == ["bravo", "bravo2", "charlie"]


def test_redact_replaces_sealed_names_only_and_counts(tmp_path, monkeypatch):
    sites_file(tmp_path, monkeypatch)
    obj = {"a": "near Bravo2 and charlie, not alpha", "n": 4.75, "l": ["Charlie's site", {"x": "bravo"}]}
    out, n = publish.redact(obj)
    assert n == 4 and out["n"] == 4.75
    assert out["a"] == f"near {publish.MARKER} and {publish.MARKER}, not alpha"
    assert out["l"][0].startswith(publish.MARKER) and out["l"][1]["x"] == publish.MARKER


def test_publish_copies_records_and_skips_manifests(tmp_path, monkeypatch):
    sites_file(tmp_path, monkeypatch)
    src = tmp_path / "models"
    (src / "model_recordings").mkdir(parents=True)
    (src / "ledger.json").write_text(json.dumps({"entries": {}}))
    (src / "probe_s.json").write_text(json.dumps({"records": [{"place": "bravo2 crater"}]}))
    (src / "manifest_s.json").write_text(json.dumps({"ids": {"c000": {"row": 1, "col": 2}}}))
    (src / "model_recordings" / "sam_x.json").write_text(json.dumps({"result": {"raw_text": "charlie"}}))
    dst = tmp_path / "pub"
    rec = publish.publish(src, dst)
    assert sorted(rec["files"]) == ["ledger.json", "model_recordings/sam_x.json", "probe_s.json"]
    assert rec["total_redactions"] == 2 and not (dst / "manifest_s.json").exists()
    assert json.loads((dst / "probe_s.json").read_text())["records"][0]["place"] == f"{publish.MARKER} crater"
    assert json.loads((dst / "PUBLISHED.json").read_text())["files"]["probe_s.json"]["redactions"] == 1
