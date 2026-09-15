import pytest

from residents import resume_studio


def test_module_exposes_produce():
    assert callable(resume_studio.produce)


def test_pipeline_is_a_stub_until_phase_1():
    with pytest.raises(NotImplementedError):
        resume_studio.produce()