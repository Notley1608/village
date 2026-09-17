import pytest
from core import config


def test_config_lists_three_video_residents(cfg):
    names = [r["name"] for r in config.residents(cfg)]
    assert names == ["shorts_history", "shorts_ai_tools", "audience_growth"]


def test_resident_zones(cfg):
    zones = {r["name"]: r["zone"] for r in config.residents(cfg)}
    assert zones == {
        "shorts_history": "gray",
        "shorts_ai_tools": "gray",
        "audience_growth": "gray",
    }


def test_config_is_free_tier_first(cfg):
    assert cfg["village"]["free_tier_first"] is True


def test_resident_by_name(cfg):
    r = config.resident_by_name(cfg, "shorts_history")
    assert r["publish_target"] == "youtube_oauth"


def test_resident_by_name_missing(cfg):
    with pytest.raises(KeyError):
        config.resident_by_name(cfg, "nope")


def test_workstream_kind_mapping(cfg):
    assert config.workstream_for_kind(cfg, "shorts_history", "short_script") == "Short scripts + assembly"
    assert config.workstream_for_kind(cfg, "shorts_ai_tools", "storyboard") == "Short scripts + assembly"
    assert config.workstream_for_kind(cfg, "audience_growth", "asset_manifest") == "Hook + format experiments"
    assert config.workstream_for_kind(cfg, "shorts_history", "unknown_kind") == "Other"
    ws = config.workstreams_of(cfg, "shorts_history")
    assert len(ws) == 1
    assert "short_script" in ws[0]["kinds"]
    assert "storyboard" in ws[0]["kinds"]
    assert "asset_manifest" in ws[0]["kinds"]


def test_video_resident_has_format_list(cfg):
    r = config.resident_by_name(cfg, "shorts_history")
    fmt = r.get("format")
    assert isinstance(fmt, list) and len(fmt) >= 2
    assert "faceless_narrated" in fmt


def test_ledger_has_monthly_cap(cfg):
    ledger = cfg.get("ledger", {})
    assert "monthly_cap_usd" in ledger
    assert ledger["monthly_cap_usd"] == 50.00
    assert "per_cycle_cap_usd" in ledger


def test_village_has_escalations_block(cfg):
    esc = cfg.get("escalations", {})
    assert "always_requires_human_approval" in esc
    approved = esc["always_requires_human_approval"]
    assert any("publishing" in item for item in approved)
