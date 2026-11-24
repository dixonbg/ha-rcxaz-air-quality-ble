"""Noise filter for the detector's ~1 Hz readings.

In steady state the readings jitter around a level (e.g. CO2 400..414 ppm).
The filter averages that jitter away with a time-based exponential moving
average, but follows a real change immediately: when ``confirm`` consecutive
readings differ from the average by more than ``jump``, the average snaps to
the new reading. The published value is the average rounded to ``step``; it
only changes when the average has moved by at least ``step * hysteresis``,
so it does not flicker between two neighbouring values.

The time step used for averaging is capped at ``MAX_STEP_S`` so that the
first reading after a gap (reconnect, restart) does not replace the average
wholesale; the average re-converges over ``tau`` instead.

With ``tau`` <= 0 the filter is disabled and every reading passes through.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MAX_STEP_S = 5.0


@dataclass(frozen=True)
class FilterParams:
    """Per-measurement filter tuning."""

    jump: float          # deviation that counts as a real change
    step: float          # resolution of the published value
    confirm: int = 2     # consecutive readings beyond ``jump`` before snapping
    hysteresis: float = 1.0


# Jump thresholds sit just above the steady-state jitter measured on a 2CO11.
DEFAULT_PARAMS: dict[str, FilterParams] = {
    "co2": FilterParams(jump=20, step=1),
    "tvoc": FilterParams(jump=0.005, step=0.001),
    "hcho": FilterParams(jump=0.003, step=0.001),
    "pm1_0": FilterParams(jump=5, step=1),
    "pm2_5": FilterParams(jump=5, step=1),
    "pm10": FilterParams(jump=5, step=1),
    "temperature": FilterParams(jump=0.3, step=0.1),
    "humidity": FilterParams(jump=2, step=1),
}


def _round_to(value: float, step: float) -> float:
    decimals = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    rounded = round(round(value / step) * step, decimals)
    return int(rounded) if step >= 1 else rounded


@dataclass
class NoiseFilter:
    """Smooths one measurement; feed it readings with ``update``."""

    params: FilterParams
    tau: float                       # averaging time constant, seconds
    _avg: float | None = field(default=None, init=False)
    _last_ts: float | None = field(default=None, init=False)
    _beyond: int = field(default=0, init=False)
    _published: float | None = field(default=None, init=False)

    def update(self, value: float, ts: float) -> float:
        """Add a reading taken at ``ts`` (seconds); return the value to publish."""
        if self.tau <= 0:
            self._published = value
            return value

        if self._avg is None:
            self._avg = float(value)
        else:
            if abs(value - self._avg) > self.params.jump:
                self._beyond += 1
            else:
                self._beyond = 0
            if self._beyond >= self.params.confirm:
                self._avg = float(value)
                self._beyond = 0
            else:
                dt = min(MAX_STEP_S, max(0.0, ts - (self._last_ts or ts)))
                alpha = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
                self._avg += alpha * (value - self._avg)
        self._last_ts = ts

        threshold = self.params.step * self.params.hysteresis
        if self._published is None or abs(self._avg - self._published) >= threshold:
            self._published = _round_to(self._avg, self.params.step)
        return self._published

    def reset(self) -> None:
        """Forget history, e.g. after a reconnect gap."""
        self._avg = self._last_ts = self._published = None
        self._beyond = 0
