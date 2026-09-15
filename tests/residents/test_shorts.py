import pytest

from residents import shorts


def test_module_exposes_produce():
    assert callable(shorts.produce)


def test_production_config(cfg):
    s = [r for r in cfg["residents"] if r["name"] == "shorts"][0]
    assert s["production"]["style"] == "stock_loops_captions"
    assert s["production"]["tts"] == "free_local"


def test_pipeline_is_a_stub_until_phase_3():
    with pytest.raises(NotImplementedError):
        shorts.produce()