"""Unit tests for the noise filter (no Home Assistant needed)."""
from __future__ import annotations

import random

from custom_components.rcxaz_air_quality.noise_filter import (
    DEFAULT_PARAMS,
    MAX_STEP_S,
    FilterParams,
    NoiseFilter,
)

CO2 = DEFAULT_PARAMS["co2"]


def _feed(f: NoiseFilter, values, start=0.0, dt=1.0):
    return [f.update(v, start + i * dt) for i, v in enumerate(values)]


def test_disabled_passes_raw_values_through():
    f = NoiseFilter(CO2, tau=0)
    assert _feed(f, [400, 414, 403]) == [400, 414, 403]


def test_steady_jitter_is_averaged_and_stays_calm():
    rnd = random.Random(1)
    raw = [rnd.randint(400, 414) for _ in range(3600)]
    out = _feed(NoiseFilter(CO2, tau=60), raw)
    settled = out[600:]
    assert min(settled) >= 404 and max(settled) <= 410
    changes = sum(1 for a, b in zip(settled, settled[1:]) if a != b)
    assert changes < 60  # raw changes ~2800 times in the same window


def test_real_jump_is_followed_immediately():
    f = NoiseFilter(CO2, tau=60)
    _feed(f, [407] * 300)
    out = _feed(f, [900, 905, 898], start=300)
    assert out[0] == 407          # one reading alone is not trusted
    assert out[1] == 905          # second consecutive one snaps


def test_single_outlier_is_ignored():
    f = NoiseFilter(CO2, tau=60)
    _feed(f, [407] * 300)
    out = _feed(f, [900, 407, 407], start=300)
    assert out == [407, 407, 407]


def test_gap_does_not_let_one_reading_replace_the_average():
    f = NoiseFilter(CO2, tau=60)
    _feed(f, [407] * 300)
    # five minutes of silence, then a reading at the noise edge
    out = f.update(414, 300 + 300)
    assert out == 407  # moved by at most MAX_STEP_S/tau of the gap
    assert MAX_STEP_S < 60


def test_fractional_steps_round_cleanly():
    f = NoiseFilter(DEFAULT_PARAMS["tvoc"], tau=60)
    out = _feed(f, [0.007] * 10)
    assert out[-1] == 0.007
    assert repr(out[-1]) == "0.007"


def test_integer_step_publishes_int():
    f = NoiseFilter(FilterParams(jump=5, step=1), tau=60)
    assert isinstance(_feed(f, [12, 13, 12])[-1], int)


def test_reset_forgets_history():
    f = NoiseFilter(CO2, tau=60)
    _feed(f, [407] * 100)
    f.reset()
    assert f.update(500, 1000) == 500
