# GTA VI launch-day Twitch audience forecaster

[![make.fun bounty](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/kby157/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/kby157/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

An entry for the make.fun bounty [gta6-twitch-ccu-forecast-01](https://make.fun/bounty/gta6-twitch-ccu-forecast-01): forecast how many people watch Grand Theft Auto VI live on Twitch in each hour of its release day, 2026-11-19 (UTC), after the first hour.

## What it does

The program reads one case file: everything recorded about the launch up to the end of hour 1, that hour's viewer count included, plus a bundle of past big game launches with their full release-day curves. A launch's day has a repeatable shape when measured relative to its own first hour, but only among launches whose first hour was already hot — rolling midnight-local unlocks like this one, as opposed to fixed-hour global unlocks whose first hour is a trickle. The forecaster pools the log viewer ratios of the hot-first-hour launches, takes the empirical quantiles of that pool for each hour, smooths them across neighbouring hours, widens the spread slightly, and scales the result by the case's own first-hour count. It writes, for each of hours 2 to 24, five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's viewer count as one JSON forecast file.

## Run it

Python 3.13, standard library only, no network. With a case directory standing in for the grader's input and output mounts:

```
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Each `<id>.in` in the input directory produces a matching `<id>.out` in the output directory.
