# Post-Tournament Workflow

How to ingest results, detect injuries, and run a post-mortem after the championship game. Total time: ~10 minutes.

## Prerequisites

Before draft day each year, run:
```bash
python src/snapshot_year.py YYYY --notes "any algorithm changes since last year"
```
This freezes `data/kenpom.csv`, `data/injuries_combined.csv`, `data/bracket.json`, and `output/projections.csv` into `archive/YYYY/`. **If you forget to snapshot before the draft, you can't honestly measure the algorithm later** — you'll be analyzing a different version than the one that drove decisions.

## Step 1 — Ingest actual results

After the championship game, gather four pieces of data from your league spreadsheet:

1. **Per-player results** — round-by-round points for every drafted player. Use `x` for DNP rounds (player didn't suit up) and `0` for played-but-scored-zero. **This distinction matters** — see Step 3.
2. **Entry totals** — per-entry round totals + final standings.
3. **Draft picks** — draft order (round, pick, entry, player).
4. **Bracket outcome** — who won each round.

Paste these into a Claude conversation. Claude will write them to:
- `archive/YYYY/actual/player_results.csv`
- `archive/YYYY/actual/entry_totals.csv`
- `archive/YYYY/actual/draft_picks.csv`
- `archive/YYYY/actual/bracket_outcome.json`

### Verification checks Claude should run automatically
- Per-player round sums equal `total_points`
- Entry roll-ups (sum of player rounds) equal reported entry totals
- Drafted players ↔ result rows match exactly (no orphans)
- 14 picks per entry
- Champion appears as the only `alive=1` team
- Player and team names match the project's existing naming convention (`Iowa St.` not `Iowa State`, `Connecticut` not `UConn`, etc.)

If any check fails, fix the data before moving on. Garbage in = garbage analysis.

## Step 2 — Detect injury candidates

```bash
python src/detect_injuries.py YYYY
```

Outputs `archive/YYYY/actual/injury_candidates.csv` and prints a short list (typically 2-5 players) flagged by these signals:
- **DNP**: player has fewer games_played than their team played
- **Cliff**: 2+ zero rounds after producing earlier in the tournament
- **Underperformance**: actual ≤ 25% of projected, on a 30+ pt projection, for a team that played 2+ rounds

The thresholds are tuned to minimize false positives. Single-game samples (1-and-done teams) are excluded — too noisy.

## Step 3 — Confirm and flag injuries

For each candidate, decide: real injury, or just bad performance?
- Google the player's name + "injury tournament" if you don't remember
- Check ESPN game logs if you want certainty
- A confirmed injury gets a note in `player_results.csv`'s `in_tournament_injury` column

Example:
```csv
Joshua Jefferson,Iowa St.,Michael D.,2,0,0,,,,3,2,0,Injured during R64; missed remainder
```

**Why this matters**: an injured player isn't a model miss, it's an unmodelable event. Including them in calibration stats poisons the algorithm signal. In 2026, one injured player (Jefferson) was distorting top-10 calibration by **12 percentage points** until we excluded him.

## Step 4 — Run the post-mortem

```bash
python src/analyze_year.py YYYY
```

Outputs to `archive/YYYY/analysis/`:
- **player_residuals.csv** — projected vs actual for every drafted player
- **calibration.csv** — top-N projection accuracy (top 10, 25, 50, 100, 150, 210)
- **bias_by_seed.csv** — average residual per seed line
- **bias_by_injury.csv** — calibration by injury status (HEALTHY, PROBABLE, etc.)
- **team_round_vs_projection.csv** — projected games vs actual rounds reached
- **draft_value.csv** — pick number vs actual points (steals & busts)

In-tournament injuries are excluded from all aggregates.

## Step 5 — Cross-year comparison

```bash
python src/compare_years.py
```

Useful starting from your second archived year. Shows:
- Algorithm SHA per year
- Calibration trend across years (top-N delta %)
- MAE / RMSE / mean residual per year
- **Persistent team bias**: teams consistently over- or under-projected across multiple years (real signal vs single-year noise)

## What to do with the findings

**Don't tune the algorithm on a single year of data.** Variance dominates with n=4 teams per seed line. A single Cinderella moves a "bias" from +0.1 to +2.0 games. Wait until you have 3+ years before drawing conclusions about systemic bias.

**Do** investigate single-year misses to understand the *mechanism*. If Florida was over-projected by ~30% across multiple players in 2026, the question isn't "how do I subtract 30% from Florida next year" — it's "did the win model give Florida an artificially easy path because of region matchups, KenPom rating, or something else?" Understanding the mechanism is what makes future improvements predictive instead of overfitted.

**Always preserve archived projections.** When you change the algorithm, never overwrite an old `projections_final.csv`. The whole point of archives is that they're frozen.

## File structure reference

```
archive/YYYY/
├── algorithm_version.txt        # git SHA + methodology notes
├── projections_final.csv        # frozen pre-draft projections
├── inputs/
│   ├── kenpom.csv
│   ├── injuries.csv
│   └── bracket.json
├── actual/
│   ├── player_results.csv       # round-by-round actual + injury column
│   ├── draft_picks.csv
│   ├── entry_totals.csv
│   ├── bracket_outcome.json
│   └── injury_candidates.csv    # generated by detect_injuries.py
└── analysis/
    ├── player_residuals.csv
    ├── calibration.csv
    ├── bias_by_seed.csv
    ├── bias_by_injury.csv
    ├── team_round_vs_projection.csv
    └── draft_value.csv
```
