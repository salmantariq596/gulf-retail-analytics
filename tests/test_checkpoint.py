"""Crash safety of the generator checkpoint (State.save / State.load)."""

from datetime import date
from types import SimpleNamespace

import pytest

from najm_gen.sim import State


def _save(path, next_day):
    State.save(SimpleNamespace(current=next_day), path)


def test_latest_checkpoint_matches_database(tmp_path):
    path = tmp_path / "full.pkl"
    _save(path, date(2025, 1, 2))
    _save(path, date(2025, 1, 3))
    assert State.load(path, expect_next_day=date(2025, 1, 3)).current == date(2025, 1, 3)
    assert (tmp_path / "full.prev").exists()


def test_crash_before_commit_uses_previous_checkpoint(tmp_path):
    # checkpoint for day N+1 written, then the crash: the database never committed day N
    path = tmp_path / "full.pkl"
    _save(path, date(2025, 1, 2))
    _save(path, date(2025, 1, 3))
    assert State.load(path, expect_next_day=date(2025, 1, 2)).current == date(2025, 1, 2)


def test_corrupt_latest_falls_back_to_previous(tmp_path):
    # what a power cut did once: the renamed file was full of zeros
    path = tmp_path / "full.pkl"
    _save(path, date(2025, 1, 2))
    _save(path, date(2025, 1, 3))
    path.write_bytes(b"\x80" + b"\x00" * 1000)
    assert State.load(path, expect_next_day=date(2025, 1, 2)).current == date(2025, 1, 2)


def test_no_matching_checkpoint_refuses(tmp_path):
    path = tmp_path / "full.pkl"
    _save(path, date(2025, 1, 2))
    with pytest.raises(RuntimeError, match="No checkpoint matches"):
        State.load(path, expect_next_day=date(2025, 6, 1))
