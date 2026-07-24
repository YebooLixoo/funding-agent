"""Unit tests for the curated score floor in web.services.scoring.

Curated sources (compute allocations + university internal-grant awareness
entries) bypass the keyword filter and must also clear the digest's score
threshold, so their per-user score is floored. Non-curated opps are untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

from web.services.scoring import (
    _CURATED_SCORE_FLOOR,
    _curated_floor,
    _curated_university_sources,
)


def _opp(source: str, source_type: str):
    return SimpleNamespace(source=source, source_type=source_type)


def test_curated_university_sources_loaded_from_config():
    # university.yaml curates the U of U internal grants under source "utah_internal".
    assert "utah_internal" in _curated_university_sources()


def test_compute_opp_is_floored():
    low = 0.12
    assert _curated_floor(_opp("cerebras_academic", "compute"), low) == _CURATED_SCORE_FLOOR


def test_curated_university_opp_is_floored():
    low = 0.20
    assert _curated_floor(_opp("utah_internal", "university"), low) == _CURATED_SCORE_FLOOR


def test_non_curated_opp_is_not_floored():
    # A grants_gov opp below the floor must keep its computed score.
    low = 0.20
    assert _curated_floor(_opp("grants_gov", "government"), low) == low


def test_floor_never_lowers_a_higher_score():
    # A curated opp that also scores high keeps its higher score (max, not set).
    high = 0.85
    assert _curated_floor(_opp("utah_internal", "university"), high) == high
