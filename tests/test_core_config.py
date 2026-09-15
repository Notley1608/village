import pytest

from core import config


def test_config_lists_three_residents(cfg):
    assert [r["name"] for r in config.residents(cfg)] == [
        "resume_studio",
        "directory",
        "shorts",
    ]


def test_resident_zones(cfg):
    zones = {r["name"]: r["zone"] for r in config.residents(cfg)}
    assert zones == {
        "resume_studio": "clean",
        "directory": "gray",
        "shorts": "gray",
    }


def test_config_is_free_tier_first(cfg):
    assert cfg["village"]["free_tier_first"] is True


def test_resident_by_name(cfg):
    r = config.resident_by_name(cfg, "directory")
    assert r["publish_target"] == "astro_static"


def test_resident_by_name_missing(cfg):
    with pytest.raises(KeyError):
        config.resident_by_name(cfg, "nope")