"""Backtest the noise filter on a Home Assistant history CSV export.

Usage: python tools/backtest.py history.csv [--tau 30 60 120]

The CSV is the "Download data" export of the History panel
(columns entity_id,state,last_changed). Entities are mapped to a
measurement by the end of their entity_id (_co2, _tvoc, _pm2_5, ...).

The export only holds state *changes*: repeated identical readings are
missing, so the average weights them slightly less than the live filter
would. Error is measured against a centred 5-minute mean of the raw data.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import pathlib
import statistics
import sys
from collections import defaultdict
from datetime import datetime

_spec = importlib.util.spec_from_file_location(
    "noise_filter",
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components/rcxaz_air_quality/noise_filter.py",
)
nf = importlib.util.module_from_spec(_spec)
sys.modules["noise_filter"] = nf
_spec.loader.exec_module(nf)

SUFFIXES = sorted(nf.DEFAULT_PARAMS, key=len, reverse=True)


def measurement_of(entity_id: str) -> str | None:
    for key in SUFFIXES:
        if entity_id.endswith("_" + key):
            return key
    return None


def load(path: str) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = measurement_of(row["entity_id"])
            if key is None:
                continue
            try:
                value = float(row["state"])
            except ValueError:
                continue  # unavailable / unknown
            ts = datetime.fromisoformat(row["last_changed"].replace("Z", "+00:00")).timestamp()
            series[key].append((ts, value))
    for rows in series.values():
        rows.sort()
    return series


def changes(values: list[float]) -> int:
    return sum(1 for a, b in zip(values, values[1:]) if a != b)


def lag_after_jumps(rows, out, jump):
    """Seconds until the output first moves after each raw jump > 3*jump."""
    lags = []
    for i in range(1, len(rows)):
        if abs(rows[i][1] - rows[i - 1][1]) > 3 * jump:
            before = out[i - 1]
            for j in range(i, len(rows)):
                if abs(out[j] - before) >= jump:
                    lags.append(rows[j][0] - rows[i][0])
                    break
    return lags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tau", type=float, nargs="+", default=[30, 60, 120])
    args = ap.parse_args()

    series = load(args.csv)
    if not series:
        sys.exit("No matching entities found in the CSV.")
    span_h = max(r[-1][0] for r in series.values()) - min(r[0][0] for r in series.values())
    print(f"Span: {span_h / 3600:.1f} h\n")
    header = f"{'sensor':12s} {'tau':>5s} {'records':>8s} {'per day':>8s} {'p95 |err|':>9s} {'mean |err|':>10s} {'jump lags (s)':>14s}"
    print(header)
    print("-" * len(header))
    totals = defaultdict(int)
    for key, rows in sorted(series.items()):
        p = nf.DEFAULT_PARAMS[key]
        raw = [v for _, v in rows]
        days = max((rows[-1][0] - rows[0][0]) / 86400, 1e-9)
        totals["raw"] += changes(raw)
        print(f"{key:12s} {'raw':>5s} {changes(raw):8d} {changes(raw) / days:8.0f}")
        for tau in args.tau:
            f = nf.NoiseFilter(p, tau)
            out = [f.update(v, ts) for ts, v in rows]
            # error vs. a centred 5-minute rolling mean of the raw data
            ref, errs, lo = [], [], 0
            window = 150
            for i, (ts, _) in enumerate(rows):
                while rows[lo][0] < ts - window:
                    lo += 1
                hi = i
                while hi + 1 < len(rows) and rows[hi + 1][0] <= ts + window:
                    hi += 1
                errs.append(abs(out[i] - statistics.fmean(raw[lo:hi + 1])))
            lags = lag_after_jumps(rows, out, p.jump)
            lag_txt = f"{len(lags)}× max {max(lags):.0f}" if lags else "no jumps"
            totals[tau] += changes(out)
            print(f"{'':12s} {tau:5.0f} {changes(out):8d} {changes(out) / days:8.0f} {sorted(errs)[int(0.95 * (len(errs) - 1))]:9.4g} {statistics.fmean(errs):10.3g} {lag_txt:>14s}")
    print("\nAll sensors: raw", totals["raw"], "| " + " | ".join(f"tau {t:g}: {totals[t]}" for t in args.tau))


if __name__ == "__main__":
    main()
