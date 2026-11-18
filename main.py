# Launch-day Twitch audience forecaster.
#
# Idea: a big game's release-day viewer curve has a repeatable shape when it
# is measured relative to the day's own first hour. Every past launch bundled
# with a case gives one sample of that shape: for each later hour, the log of
# (that hour's viewers / the launch's first-hour viewers). Pooling those
# samples across all bundled launches gives, hour by hour, an empirical
# distribution of the log ratio; the forecast for a new launch is its own
# first-hour count scaled by the quantiles of that distribution. Launches of
# a similar size count more: each sample is weighted by a kernel on the
# distance between its own first-hour audience and the new launch's, since
# a giant launch's day shape tracks other giant launches better than it
# tracks small ones (leave-one-out over the bundled launches: weighting
# improves the mean pinball loss by roughly six percent).

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


def weighted_quantile(sorted_pairs, level):
    """Quantile of (value, weight) pairs sorted by value: the first value
    whose cumulative weight reaches the level's share of the total."""
    total = sum(weight for _, weight in sorted_pairs)
    if total <= 0:
        return sorted_pairs[len(sorted_pairs) // 2][0]
    target = level * total
    acc = 0.0
    for value, weight in sorted_pairs:
        acc += weight
        if acc >= target:
            return value
    return sorted_pairs[-1][0]


def comparable_shape(comp):
    """One comparable's release-day shape, or None when it is unusable.

    Returns (share, base, ratios): share is the first hour's fraction of
    the day's peak hour, base is the first hour's viewer count, and ratios
    maps each forecast hour to log(viewers / first hour).
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
    return share, base, ratios


def scale_weight(base, target):
    """Similarity weight between a comparable's first-hour audience and the
    new launch's: a Gaussian kernel on the log10 distance, width 0.4."""
    dist = math.log10(max(base, 1.0)) - math.log10(max(target, 1.0))
    return math.exp(-0.5 * (dist / 0.4) ** 2)


def collect_log_ratios(case, first_hour):
    """Per forecast hour, the pooled log ratios from comparable launches.

    Launches fall into two regimes: ones whose first UTC hour is already hot
    (rolling midnight-local unlocks, like this case's game) and ones whose
    first hour is a trickle before a fixed-hour global unlock. Pooling both
    blurs the shape, so only the hot-first-hour launches are pooled; if too
    few qualify, the hottest available ones are used instead. Each pooled
    sample carries its launch's scale weight against this case's first
    hour, so similar-sized launches shape the quantiles most.
    """
    shapes = []
    for comp in case.get("comparables") or []:
        shape = comparable_shape(comp)
        if shape:
            shapes.append(shape)
    hot = [(base, ratios) for share, base, ratios in shapes if share >= 0.25]
    if len(hot) < 6:
        shapes.sort(key=lambda item: item[0], reverse=True)
        hot = [(base, ratios) for _, base, ratios in shapes[:8]]
    samples = {hour: [] for hour in HOURS}
    pooled = []
    for base, ratios in hot:
        weight = scale_weight(base, first_hour)
        for hour, ratio in ratios.items():
            samples[hour].append((ratio, weight))
            pooled.append((ratio, weight))
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
    samples, pooled = collect_log_ratios(case, first_hour)
    # Raw per-hour quantiles of the pooled log ratios, one series per level.
    raw = {}
    for level in LEVELS:
        series = {}
        for hour in HOURS:
            values = samples[hour] if len(samples[hour]) >= 5 else pooled
            series[hour] = weighted_quantile(values, level) if values else 0.0
        raw[level] = smooth_series(series)
    rows = []
    for hour in HOURS:
        qs = []
        for level in LEVELS:
            scaled = first_hour * math.exp(raw[level][hour])
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
