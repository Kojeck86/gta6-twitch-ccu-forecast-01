"""gta6-twitch-ccu-forecast-01: launch-curve forecaster for GTA VI Twitch viewers.

Reads one case file (makefun/twitch-ccu-case/v1) from /input (or
$MAKEFUN_INPUT_DIR) and writes one forecast to /output (or
$MAKEFUN_OUTPUT_DIR): for each of hours 2..24 of the release day, five
quantiles (5%, 25%, 50%, 75%, 95%) of that hour's concurrent Twitch viewers
in the "Grand Theft Auto VI" category.

Method (standard library only, deterministic, no network):
  The case carries the release-day hourly curves of past big game launches
  ("comparables"). For each comparable we compute its log-ratio curve
  log(viewers[h] / viewers[1]) over the release day. A launch whose hour-1
  print is a tiny fraction of its own peak (a simultaneous global unlock
  hours later, or a slow-burn launch) has a ratio curve that explodes and
  says nothing about a rolling-midnight launch like GTA VI, so donors are
  restricted to launches already substantially live at hour 1 (hour-1 print
  at least 15% of their own release-day peak). The forecast's quantiles are
  the scale-weighted empirical quantiles of those donors' log-ratio curves,
  anchored on this case's hour-1 print: donors whose hour-1 level is close
  to the target's (in log space, Gaussian kernel, bandwidth 1.0) count more,
  because the biggest launches rise through their release day differently
  from small ones. The spread therefore comes from real launch-to-launch
  variation, measured across dozens of launches, not from a guessed sigma.

  If no donor survives the filter (or the case carries no comparables at
  all), the forecast falls back to the persistence baseline shape: every
  hour at the hour-1 print with a random-walk spread of 0.15 log units per
  root hour. The output is always valid: exactly 23 rows, hours 2..24,
  five finite numbers per row, each above 0 and at most 1e9, non-decreasing.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim, standard library only: no network, no pip packages.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# finds a model.py shipped beside this file (none is shipped; the line is kept
# for the same layout the starter documents).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level (used only by the fallback).
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# The spread of an hour's move in the fallback, in natural-log units per
# square-root hour (the house persistence baseline's sigma).
FALLBACK_SIGMA = 0.15

# Donor filter: a comparable launch only counts if its hour-1 print was at
# least this fraction of its own release-day peak. Below it, the launch was
# not yet live at hour 1 (a later simultaneous unlock, or a slow burn) and
# its ratio curve is a different animal.
MIN_R1_PEAK = 0.15
# Scale kernel: donors are weighted by how close their hour-1 level is to
# the target's, in log space, with this Gaussian bandwidth.
SCALE_BW = 1.0


def parse_time(text):
    """Parse an ISO-8601 timestamp with a Z suffix into an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100.

    A whole number comes back as an int, so json.dumps writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def weighted_quantile(pairs, tau):
    """Weighted quantile of [(value, weight), ...]; values need not be sorted."""
    ordered = sorted(pairs, key=lambda p: p[0])
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= tau * total:
            return value
    return ordered[-1][0]


def donor_curves(comparables):
    """Build the donor pool from the case's comparables.

    Returns a list of (hour1_viewers, {hour: log-ratio to hour 1}) for every
    comparable with a complete, positive release day (hours 1..24 present).
    """
    donors = []
    for comp in comparables or []:
        hourly = comp.get("hourly") or []
        day_start = comp.get("day_start")
        if not day_start:
            continue
        try:
            start = parse_time(day_start)
        except (TypeError, ValueError):
            continue
        day = {}
        for point in hourly:
            try:
                when = parse_time(point["from"])
                viewers = point["viewers"]
            except (KeyError, TypeError, ValueError):
                continue
            offset = (when - start).total_seconds()
            if 0 <= offset < 24 * 3600:
                hour = int(offset // 3600) + 1
                day[hour] = viewers
        if len(day) != 24:
            continue
        if any((not isinstance(v, (int, float))) or v <= 0 for v in day.values()):
            continue
        peak = max(day.values())
        donors.append((day[1], day, day[1] / peak))
    return donors


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    # The hours to forecast, in order (the case lists 2..24; sort so the
    # output order never depends on the input file's row order).
    hours = sorted(row["hour"] for row in case["forecast"])

    donors = donor_curves(case.get("comparables"))
    # Keep only launches already substantially live at hour 1; if the filter
    # empties the pool, fall back to every complete donor.
    live = [d for d in donors if d[2] >= MIN_R1_PEAK]
    pool = live if live else donors

    rows = []
    log_p1 = math.log(p1)
    for h in hours:
        if pool:
            pairs = []
            for day1, day, _ratio in pool:
                weight = math.exp(-((math.log(day1) - log_p1) ** 2) / (2 * SCALE_BW * SCALE_BW))
                pairs.append((math.log(day[h] / day[1]), weight))
            quantiles = [weighted_quantile(pairs, tau) for tau in LEVELS]
            values = [p1 * math.exp(q) for q in quantiles]
        else:
            # No usable donor at all: the persistence baseline shape.
            spread = FALLBACK_SIGMA * math.sqrt(h - 1)
            values = [p1 * math.exp(z * spread) for z in Z]
        # Round to 2 decimals half up, keep every value valid and the row
        # non-decreasing even after rounding.
        rounded = []
        floor = 0.01
        for value in values:
            got = round2(max(floor, value))
            if rounded:
                got = max(got, rounded[-1])
            got = min(got, 1000000000)
            rounded.append(got)
        rows.append({"hour": h, "q": rounded})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
