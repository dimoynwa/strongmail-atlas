import pytest

from general_agent.models import clamp_limit


def test_clamp_limit_defaults():
    assert clamp_limit() == 10


def test_clamp_limit_caps_at_max():
    assert clamp_limit(100) == 50


def test_clamp_limit_floors_at_one():
    assert clamp_limit(0) == 1
