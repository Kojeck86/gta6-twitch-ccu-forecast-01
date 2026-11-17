[![gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Kojeck86/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Kojeck86/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU Forecaster

A program that forecasts, hour by hour, how many people will be watching
Grand Theft Auto VI live on Twitch over the 24 UTC hours of its release day
(19 November 2026), from everything recorded up to the end of its first
hour — that hour's print included. For each of hours 2 to 24 it writes five
quantiles (5%, 25%, 50%, 75%, 95%) of that hour's concurrent viewer count.
Scored by mean pinball loss on the log scale; the lowest loss wins.

## How it works

The case file carries the release-day hourly curves of past big game
launches ("comparables"). For each comparable the program computes its
log-ratio curve, `log(viewers[h] / viewers[1])`, over the release day.

Two things make a naive median over all launches lose:

1. **Not every launch was live at hour 1.** A launch with a simultaneous
   global unlock hours into the day (or a slow burn) has an hour-1 print
   that is a tiny fraction of its peak, so its ratio curve explodes to
   100x and says nothing about a rolling-midnight launch like GTA VI.
   Donors are therefore restricted to launches already substantially live
   at hour 1: hour-1 print at least 15% of their own release-day peak.
2. **Big launches rise differently from small ones.** Donors are weighted
   by how close their hour-1 level is to the target's (log space,
   Gaussian kernel, bandwidth 1.0), so the biggest launches — the best
   analogues for the biggest launch ever — count most.

The forecast's quantiles are the scale-weighted empirical quantiles of
those donors' log-ratio curves, anchored on the case's hour-1 print. The
spread is therefore measured from real launch-to-launch variation across
dozens of launches, not guessed. If no donor survives the filter, the
program falls back to the persistence baseline shape (every hour at the
hour-1 print, random-walk spread 0.15 log units per root hour), so the
output is always valid.

Standard library only, deterministic, no network. Run it with:

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Local validation

Leave-one-out over the 37 comparable launches with a full release day,
run end to end through the shipped `main.py` (each launch forecast from
the other 36, scored with the official pinball loss on the log scale):

| subset | this model | house baseline |
|---|---|---|
| launches already live at hour 1 (24; GTA VI's kind) | **0.205** mean loss | 0.265 |
| practice-like launches (14) | **0.498** mean loss | 0.586 |
| all 37 launches | **0.771** mean loss | 0.930 |

The model beats the house persistence baseline on 20 of 24 launches of
GTA VI's kind and 12 of 14 practice-like launches. The house baseline's
own practice result is 0.387; the four practice cases are scored by the
server, so that number is a server-side check, not a local one.

The program was also run on all four practice cases (p00–p03): every
output is valid (23 rows, hours 2–24, five finite numbers per row, each
above 0 and at most 1e9, non-decreasing), deterministic (two runs write
byte-identical files), and fast (all four cases in well under a second).
