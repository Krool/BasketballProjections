# Post-Tournament Workflow

How to ingest results, detect injuries, run the post-mortem, and update the website after the championship game. Total time: ~10 minutes once you have the data in front of you.

## Prerequisites

Before draft day each year, you should have run:
```bash
python src/snapshot_year.py YYYY --notes "any algorithm changes since last year"
```
This freezes all projection inputs and the projection output into `archive/YYYY/`. **If you forget to snapshot before the draft, you can't honestly measure the algorithm later** — you'll be analyzing a different version than the one that drove the actual draft picks.

The snapshot captures: `kenpom.csv` + raw + tournament filter, `injuries_combined.csv` + `injury_overrides.csv`, `bracket.json`, `all_player_stats.csv`, the per-team `data/player_stats/` cache, `docs/insights.json`, and `output/projections.csv`. It also records the git SHA + commit message in `algorithm_version.txt`.

---

## Step 1 — Ingest actual results

After the championship game, gather four pieces of data from your league spreadsheet:

1. **Per-player results** — round-by-round points for every drafted player. Use `x` for DNP rounds (player didn't suit up) and `0` for played-but-scored-zero. **This distinction matters** — see Step 3.
2. **Entry totals** — per-entry round totals + final standings.
3. **Draft picks** — full draft order (round, pick, entry, player).
4. **Bracket outcome** — who won each game, ideally with scores.

Paste these into a Claude conversation. Claude writes them to:
- `archive/YYYY/actual/player_results.csv`
- `archive/YYYY/actual/entry_totals.csv`
- `archive/YYYY/actual/draft_picks.csv`
- `archive/YYYY/actual/bracket_outcome.json`

Claude also normalizes team and player names against `data/player_aliases.csv` and joins ESPN player IDs from `archive/YYYY/inputs/all_player_stats.csv`.

### Verification checks Claude runs automatically
- Per-player round sums equal `total_points`
- Entry roll-ups (sum of player rounds) equal reported entry totals
- Drafted players ↔ result rows match exactly (no orphans)
- 14 picks per entry (or whatever your league size is)
- Player and team names match the project's canonical names (e.g., `Iowa St.` not `Iowa State`, `Connecticut` not `UConn`)
- ESPN player IDs match for ≥99% of drafted players

### CRITICAL: Verify the champion externally
**Do not trust the league spreadsheet's `alive=1` column or its players_left counts.** In 2026, the spreadsheet had UConn marked as the survivor when Michigan actually won. Always cross-check the champion against [Wikipedia](https://en.wikipedia.org/wiki/2027_NCAA_Division_I_men%27s_basketball_tournament) or [NCAA.com](https://www.ncaa.com/march-madness) before moving on.

**Post-tournament, all players have `alive=0`** — nobody is alive after the championship game ends. The "alive" column is only meaningful mid-tournament.

---

## Step 2 — Detect injury candidates

```bash
python src/detect_injuries.py YYYY
```

Outputs `archive/YYYY/actual/injury_candidates.csv` and prints a short list (typically 2-5 players) flagged by these signals:
- **DNP**: player has fewer `games_played` than their team played (counts only `x`, not `0`)
- **Cliff**: 2+ zero rounds after producing earlier in the tournament
- **Underperformance**: actual ≤ 25% of projected, on a 30+ pt projection, for a team that played 2+ rounds

The thresholds are tuned to minimize false positives. Single-game samples (1-and-done teams) are excluded — too noisy. Magic numbers live at the top of the script if you want to tweak.

---

## Step 3 — Confirm and flag injuries

For each candidate, decide: real injury, or just bad performance?
- Google the player's name + "injury tournament" if you don't remember
- Check ESPN game logs if you want certainty
- A confirmed injury gets a note in the `in_tournament_injury` column of `player_results.csv`

Example row:
```csv
Joshua Jefferson,Iowa St.,Michael D.,...,Injured during R64; missed remainder
```

### Why this matters
An injured player isn't a model miss, it's an unmodelable event. Including them in calibration stats poisons the algorithm signal. In 2026, one injured player (Joshua Jefferson) was distorting top-10 calibration by **12 percentage points** until we excluded him. Tyler Bilodeau (UCLA) was the second confirmed 2026 injury.

### Played through injury vs missed games
A player who **played hurt but didn't miss any games** (e.g., Yaxel Lendeborg with an MCL/ankle injury in the 2026 championship) should NOT be flagged. Their actual stat line *is* the right thing to measure. Only flag players who actually missed playing time.

---

## Step 4 — Run the post-mortem

```bash
python src/analyze_year.py YYYY
```

Outputs to `archive/YYYY/analysis/`:

| File | Contents |
|---|---|
| `player_residuals.csv` | Projected vs actual for every drafted player |
| `calibration.csv` | Top-N projection accuracy (top 10, 25, 50, 100, 150, 210) |
| `bias_by_seed.csv` | Average residual per seed line |
| `bias_by_injury.csv` | Calibration by injury status (HEALTHY, PROBABLE, etc.) |
| `team_round_vs_projection.csv` | Projected games vs actual rounds reached per team |
| `draft_value.csv` | Pick number vs actual points (steals & busts) |
| `draft_efficiency.csv` | Per-entry: actual score vs simulated algo-following score vs rank-baseline |
| `entry_post_mortem.csv` | Per-entry MAE, mean residual, hit rate vs projection |

In-tournament injuries are excluded from all aggregates.

---

## Step 5 — Build website JSON

```bash
python src/build_archive_json.py YYYY
```

Generates:
- `docs/archive/<year>.json` — bundled history data (~140 KB) consumed by the History view
- `docs/archive/<year>_players.json` — players.json-shaped feed for the `{Year} Draft` redraft tab (so you can mock-draft against historical projections)
- `docs/archive/index.json` — list of all archived years (the website auto-generates tabs from this)

This step also runs **schema validation** on `player_results.csv`, `draft_picks.csv`, `entry_totals.csv`, and `bracket_outcome.json` via `src/archive_schema.py`. Any missing columns or bracket-game inconsistencies print as warnings — fix them before committing.

The website tab bar will automatically show `{YYYY} Summary` and `{YYYY} Draft` tabs once `index.json` lists the year.

---

## Step 6 — Cross-year comparison (year 2+)

```bash
python src/compare_years.py
```

Useful starting from your second archived year. Shows:
- Algorithm SHA per year
- Calibration trend across years (top-N delta %)
- MAE / RMSE / mean residual per year
- **Persistent team bias**: teams consistently over- or under-projected across multiple years (real signal vs single-year noise)

---

## Step 7 — Bump Selection Sunday + commit + push

1. Edit `docs/index.html` and bump the `SELECTION_SUNDAY` constant to next year's date so the upcoming-year tab labels and countdown work.
2. Stage everything in `archive/<year>/` and `docs/archive/<year>*.json`.
3. Commit with a message that includes the champion + winning entry + headline metrics.
4. `git push origin master` — GitHub Pages picks up changes within 1-2 minutes.

---

## What to do with the findings

**Don't tune the algorithm on a single year of data.** Variance dominates with n=4 teams per seed line. A single Cinderella moves a "bias" from +0.1 to +2.0 games. Wait until you have 3+ years before drawing conclusions about systemic bias.

**Do** investigate single-year misses to understand the *mechanism*. If a region is over-projected by ~30% across multiple players, the question isn't "how do I subtract 30% next year" — it's "did the win model give that region an artificially easy path because of region matchups, KenPom rating, or something else?" Understanding the mechanism is what makes future improvements predictive instead of overfitted.

**Always preserve archived projections.** When you change the algorithm, never overwrite an old `projections_final.csv`. The whole point of archives is that they're frozen.

---

## Quick reference: file structure after a complete year

```
archive/YYYY/
├── algorithm_version.txt
├── projections_final.csv
├── inputs/
│   ├── kenpom.csv, kenpom_raw.txt, kenpom_tournament.csv
│   ├── injuries.csv, injury_overrides.csv
│   ├── bracket.json
│   ├── all_player_stats.csv
│   ├── player_stats/
│   └── insights.json
├── actual/
│   ├── player_results.csv      # round-by-round actual + injury column
│   ├── draft_picks.csv         # full draft order with espn_ids
│   ├── entry_totals.csv        # per-entry round totals + final standings
│   ├── bracket_outcome.json    # round-by-round survivors + games[] with scores
│   └── injury_candidates.csv   # detect_injuries output
└── analysis/
    ├── player_residuals.csv
    ├── calibration.csv
    ├── bias_by_seed.csv
    ├── bias_by_injury.csv
    ├── team_round_vs_projection.csv
    ├── draft_value.csv
    ├── draft_efficiency.csv
    └── entry_post_mortem.csv

docs/archive/
├── index.json                  # list of archived years (drives website tabs)
├── YYYY.json                   # bundled history data
└── YYYY_players.json           # redraft players feed
```
