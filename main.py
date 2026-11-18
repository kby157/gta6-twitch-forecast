# Launch-day Twitch audience forecaster.
#
# Idea: a big game's release-day viewer curve has a repeatable shape when it
# is measured relative to the day's own first hour. Every past launch bundled
# with a case gives one sample of that shape: for each later hour, the log of
# (that hour's viewers / the launch's first-hour viewers). Pooling those
# samples across all bundled launches gives, hour by hour, an empirical
# distribution of the log ratio; the forecast for a new launch is its own
# first-hour count scaled by the quantiles of that distribution.

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
HOURS = list(range(2, 25))


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hourly_viewers(points):
    """Map each point's hour-start moment to its viewer count."""
    table = {}
    for point in points or []:
        try:
            viewers = point.get("viewers")
            if viewers is None or viewers <= 0:
                continue
            table[parse_ts(point["from"])] = float(viewers)
        except Exception:
            continue
    return table


def quantile(sorted_values, level):
    """Linear-interpolated quantile of an ascending list."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = level * (n - 1)
    low = int(math.floor(pos))
    high = min(low + 1, n - 1)
    frac = pos - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def comparable_shape(comp):
    """One comparable's release-day shape, or None when it is unusable.

    Returns (share, ratios): share is the first hour's fraction of the day's
    peak hour, ratios maps each forecast hour to log(viewers / first hour).
    """
    try:
        start = parse_ts(comp["day_start"])
    except Exception:
        return None
    table = hourly_viewers(comp.get("hourly"))
    base = table.get(start)
    if not base:
        return None
    day = {}
    for hour in [1] + HOURS:
        value = table.get(start + timedelta(hours=hour - 1))
        if value:
            day[hour] = value
    if len(day) < 20:
        return None
    share = base / max(day.values())
    log_base = math.log(base)
    ratios = {hour: math.log(value) - log_base
              for hour, value in day.items() if hour != 1}
    return share, ratios


def collect_log_ratios(case):
    """Per forecast hour, the pooled log ratios from comparable launches.

    Launches fall into two regimes: ones whose first UTC hour is already hot
    (rolling midnight-local unlocks, like this case's game) and ones whose
    first hour is a trickle before a fixed-hour global unlock. Pooling both
    blurs the shape, so only the hot-first-hour launches are pooled; if too
    few qualify, the hottest available ones are used instead.
    """
    shapes = []
    for comp in case.get("comparables") or []:
        shape = comparable_shape(comp)
        if shape:
            shapes.append(shape)
    hot = [ratios for share, ratios in shapes if share >= 0.25]
    if len(hot) < 6:
        shapes.sort(key=lambda item: item[0], reverse=True)
        hot = [ratios for _, ratios in shapes[:8]]
    samples = {hour: [] for hour in HOURS}
    pooled = []
    for ratios in hot:
        for hour, ratio in ratios.items():
            samples[hour].append(ratio)
            pooled.append(ratio)
    for hour in HOURS:
        samples[hour].sort()
    pooled.sort()
    return samples, pooled


def smooth_series(series):
    """Three-hour moving average of a per-hour series, two at the edges."""
    smoothed = {}
    for i, hour in enumerate(HOURS):
        values = [series[hour]]
        if i > 0:
            values.append(series[HOURS[i - 1]])
        if i < len(HOURS) - 1:
            values.append(series[HOURS[i + 1]])
        smoothed[hour] = sum(values) / len(values)
    return smoothed


def forecast_case(case):
    known = case.get("known") or []
    first_hour = 1.0
    if known:
        viewers = known[0].get("viewers") or 0
        first_hour = max(float(viewers), 1.0)
    samples, pooled = collect_log_ratios(case)
    # Raw per-hour quantiles of the pooled log ratios, one series per level.
    raw = {}
    for level in LEVELS:
        series = {}
        for hour in HOURS:
            values = samples[hour] if len(samples[hour]) >= 5 else pooled
            series[hour] = quantile(values, level) if values else 0.0
        raw[level] = smooth_series(series)
    median = raw[0.5]
    rows = []
    for hour in HOURS:
        qs = []
        for level in LEVELS:
            # Widen the smoothed spread slightly around the median: pooled
            # launches vary a little more than the pool's own quantiles say.
            log_q = median[hour] + (raw[level][hour] - median[hour]) * 1.1
            scaled = first_hour * math.exp(log_q)
            qs.append(min(max(scaled, 1.0), 1_000_000_000.0))
        for i in range(1, len(qs)):
            if qs[i] < qs[i - 1]:
                qs[i] = qs[i - 1]
        rows.append({"hour": hour, "q": qs})
    return {"hours": rows}


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(input_dir.glob("*.in")):
        with open(path, "r", encoding="utf-8") as handle:
            case = json.load(handle)
        result = forecast_case(case)
        out_path = output_dir / (path.name[:-3] + ".out")
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle)


if __name__ == "__main__":
    main()
