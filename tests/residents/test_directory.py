import pytest

from residents import directory


def test_module_exposes_produce():
    assert callable(directory.produce)


def test_launch_config_geometry(cfg):
    d = [r for r in cfg["residents"] if r["name"] == "directory"][0]
    assert d["launch_volume"]["money_pages"] == 10
    assert d["launch_volume"]["hub_pages"] == 5


def test_pipeline_is_a_stub_until_phase_2():
    with pytest.raises(NotImplementedError):
        directory.produce()