# March Madness Player Tourney

Fantasy draft board and historical recap for March Madness player pools. Projects which players will score the most total points across the NCAA tournament based on KenPom efficiency ratings, recent form, and injury data. After each tournament, archives the projections + actuals so the algorithm can be measured and improved across years.

**Live site**: [krool.github.io/BasketballProjections](https://krool.github.io/BasketballProjections/) or open `docs/index.html` over HTTP locally (CORS blocks `file://`):
```bash
cd docs && python -m http.server 8000  # then visit http://localhost:8000
```

The site has three kinds of tabs in the header — see [Website](#website-docsindexhtml).

---

## Project layout

```
src/                                  # Python pipeline + analysis
  main.py                             # 7-step pipeline orchestrator
  parse_kenpom.py                     # raw KenPom paste → CSV
  scrape_players_espn.py              # ESPN player stats + game logs + ESPN_TEAM_IDS map
  scrape_injuries.py                  # injury loader (manual overrides + ESPN)
  simulate_bracket.py                 # win probability + bracket propagation + per-round opponent context
  project_points.py                   # final projection: PPG × expected_games × adjustments
  update_first_four.py                # edit bracket.json after play-in games are decided
  snapshot_year.py                    # freeze data/ + output/ → archive/<year>/ before draft day
  detect_injuries.py                  # heuristic scanner for in-tournament injury candidates
  analyze_year.py                     # post-mortem: residuals, calibration, bias, draft efficiency
  build_archive_json.py               # archive CSVs → docs/archive/<year>.json + <year>_players.json
  build_team_logos.py                 # ESPN_TEAM_IDS → docs/team_logos.json
  compare_years.py                    # cross-year algorithm performance trends
  archive_schema.py                   # field-name constants + validators (single source of truth)

data/                                 # pipeline inputs (live working state for current year)
  bracket.json                        # 64-team bracket
  first_four.json                     # play-in matchups (used by main.py until decided)
  injury_overrides.csv                # manual injury statuses (authoritative)
  injuries_combined.csv               # generated: merged ESPN + manual
  kenpom_raw.txt                      # raw KenPom paste (you create this)
  kenpom.csv                          # parsed: all 365 D1 teams
  kenpom_tournament.csv               # filtered: 68 tournament teams with seeds
  all_player_stats.csv                # combined player stats with ESPN IDs
  player_stats/                       # per-team JSON cache + _recent_form.json
  player_aliases.csv                  # known name variants for ingest normalization

archive/<year>/                       # frozen draft year (do not modify after the season)
  algorithm_version.txt               # git SHA + methodology + post-mortem summary
  projections_final.csv               # frozen pre-draft projection
  inputs/                             # frozen pipeline inputs (full snapshot)
  actual/                             # post-tournament data (player_results, draft_picks,
                                      #   entry_totals, bracket_outcome, injury_candidates)
  analysis/                           # generated post-mortem CSVs

output/
  projections.csv                     # current-year projection output

docs/                                 # GitHub Pages SPA
  index.html                          # ~3700-line single page app
  players.json                        # current-year projection feed (auto-deployed by main.py)
  insights.json                       # manual scouting notes for tooltips
  team_logos.json                     # ESPN team-id map (generated from scrape_players_espn.py)
  archive/
    index.json                        # list of available archived years
    <year>.json                       # bundled history data per year
    <year>_players.json               # players.json-shaped feed for the {Year} Draft tab
  sw.js                               # service worker (offline cache)
  manifest.json, icon-*.png           # PWA assets
  post_tournament_workflow.md         # step-by-step guide for ingesting a finished season
```

---

## Annual workflow

### 1. Update KenPom data (after Selection Sunday)
1. Copy the ratings table from [kenpom.com](https://kenpom.com)
2. Paste into `data/kenpom_raw.txt`
3. `python src/parse_kenpom.py` — generates `kenpom.csv` and `kenpom_tournament.csv`
4. Verify `kenpom_tournament.csv` has all 68 tournament teams with correct seeds

### 2. Update the bracket
Edit `data/bracket.json` with the 64-team bracket:
```json
{
  "regions": {
    "East":    { "1": "TeamName", "16": "TeamName", "8": "...", ... },
    "West":    { ... },
    "Midwest": { ... },
    "South":   { ... }
  },
  "final_four_matchups": [["East", "West"], ["South", "Midwest"]]
}
```
Team names must match KenPom exactly (e.g., `Iowa St.` not `Iowa State`).

### 3. Update ESPN team IDs + regenerate `team_logos.json`
In `src/scrape_players_espn.py`, update `ESPN_TEAM_IDS` for any new tournament teams (the numeric IDs from ESPN URLs, e.g., `espn.com/.../id/150` → Duke = 150). Then:
```bash
python src/build_team_logos.py
```
This regenerates `docs/team_logos.json`, the single source of truth for team logos used by the website.

### 4. Update First Four matchups
Edit `data/first_four.json` with the new play-in matchups:
```json
{ "year": 2027, "matchups": [["TeamA", "TeamB"], ...] }
```
Both teams in each pair stay draftable until one is in `bracket.json` and the other isn't. After play-ins finish, run `python src/update_first_four.py` to write the winners into `bracket.json`.

### 5. Update injury data
Edit `data/injury_overrides.csv` (the authoritative source — ESPN's injury page is unreliable):
```csv
player,team,status,games_missed,fitness,notes
Player Name,Team,OUT,6,0,ACL tear - season ending
```
Status values: `OUT`, `DAY-TO-DAY`, `PROBABLE`, `RETURNING`, `HEALTHY`. `games_missed` is the number of tournament rounds the player will skip (0-6); `fitness` is a 0-1 multiplier for the rounds they DO play.

### 6. Update player aliases (optional, only if your league spreadsheet uses different names)
Append to `data/player_aliases.csv` any name variants between your league source and the project's canonical names. This file is only consumed during post-tournament ingest, but maintaining it incrementally beats re-mapping each year.

### 7. Clear caches and regenerate
```bash
rm -rf data/player_stats/                   # ESPN player stat cache
rm -f data/all_player_stats.csv             # combined stats
rm -f data/player_stats/_recent_form.json   # game log cache
python src/main.py                          # full pipeline → output/projections.csv + docs/players.json
```

### 8. Update insights (optional)
Edit `docs/insights.json` with scouting notes per player:
```json
{ "Player Name": "Note shown as a tooltip on the draft board" }
```

### 9. Snapshot before draft day
```bash
python src/snapshot_year.py 2027 --notes "what changed in the algo since 2026"
```
Freezes everything in `data/` + `output/projections.csv` into `archive/2027/`. Records git SHA + commit message. **Do this before the draft happens** — without it you can't honestly measure algorithm performance later.

### 10. Update Selection Sunday date
Bump the `SELECTION_SUNDAY` constant in `docs/index.html` to next year's date so the upcoming-year tab and countdown work.

### 11. After the tournament
See [`docs/post_tournament_workflow.md`](docs/post_tournament_workflow.md) for ingesting results, detecting injuries, running the post-mortem, and rebuilding the website JSON.

---

## Pipeline Steps (`src/main.py`)

The pipeline runs 7 steps:

1. **Load KenPom data** — Team ratings (AdjO, AdjD, AdjT) from `kenpom_tournament.csv`
2. **Load bracket** — 64-team bracket from `bracket.json`
3. **Load/scrape player stats** — Per-player PPG, RPG, APG from ESPN. Cached in `data/player_stats/`. Also captures ESPN player IDs for game log scraping and team logos.
4. **Load injuries** — Manual overrides from `injury_overrides.csv` + ESPN scrape (best-effort). Manual overrides take precedence.
5. **Adjust KenPom + simulate bracket** — Reduce AdjO for teams with OUT players, then propagate win probabilities through the bracket tree to compute expected games per team. Also computes per-round opponent context (DRtg, AdjT, margin) for matchup adjustments.
6. **Scrape recent form** — Game logs from ESPN for players with 12+ PPG. Computes last-5-game average. Cached in `_recent_form.json`.
7. **Project points** — Combine all data into final projections. Writes `output/projections.csv` and deploys `docs/players.json`.

## Projection Model

### Formula
```
projected_points = Σ over rounds r of P(team plays round r) × adjusted_PPG_r
adjusted_PPG_r  = ppg × pace_factor_r × defense_factor_r × fitness_mult
```
Players with `games_missed > 0` have those rounds skipped before the per-round sum.

### Factors

**Win probability** (drives expected games):
```
P(A beats B) = 1 / (1 + 10^(-margin / 20))
margin       = (AdjO_A - AdjD_A) - (AdjO_B - AdjD_B)
```
Divisor of 20 calibrated for tournament single-elimination variance. Team quality drives results — not seed labels.

**Recent form blending**:
```
effective_PPG = 60% × season_PPG + 40% × last_5_games_PPG
```
Captures hot/cold streaks entering the tournament. Only applied to players with 12+ season PPG (where we have game log data). Others use flat season average.

**Pace normalization** (per round):
```
pace_factor = (team_AdjT + opponent_AdjT) / 2 / team_AdjT
```
Adjusts for tempo mismatches. Range: ~±6%.

**Opponent defense** (per round):
```
defense_factor = opponent_DRtg / 100.0
```
Scales scoring by opponent quality. Range: ~±11%. Opponents are probability-weighted across the bracket.

**Injury model** (player level):
| Status | games_missed | fitness | Notes |
|---|---|---|---|
| HEALTHY    | 0 | 1.00 | Default |
| PROBABLE   | 0 | 0.90 | Expected to play, minor issue |
| RETURNING  | 0 | 0.80 | Back from injury, may have rust |
| DAY-TO-DAY | 0-1 | 0.50-0.75 | Hand-tuned per case in `injury_overrides.csv` |
| OUT (game) | 1+ | 1.00 | Misses N rounds, full strength when back |
| OUT (season) | 6 | 0 | Replaced flat multiplier — `games_missed` is the primary signal |

The model multiplies remaining-game scoring by `fitness_mult`. `games_missed` rounds are skipped entirely from the per-round sum.

**Injury-adjusted KenPom** (team level):
```
loss_rate      = 0.35 + (0.10 if player_ppg ≥ 20)
AdjO_reduction = (ppg × loss_rate / team_total_ppg) × (AdjO - 107)
```
Only applied for OUT players. Reduces team's offensive efficiency before bracket simulation.

### What we tested and removed
These factors were implemented, tested against historical data, and removed because they either had no evidence or didn't change draft rankings:
- **Tournament scoring surge** (+8% for stars) — Only supported by survivorship-biased data. Sensitivity test: changed 0 picks in top 30.
- **Scoring concentration** (boost go-to scorers) — Historical data showed no effect (high-share players surged 1.18x vs low-share 1.22x).
- **Blowout minutes reduction** — Historical data showed the opposite: stars score MORE in blowouts.

---

## Website (`docs/index.html`)

Single SPA with three kinds of tabs in the header bar (always visible at the top):

- **`{Year} Draft`** (e.g., `2027 Draft`) — the upcoming season. Pre-Selection-Sunday shows a centered countdown clock with the tagline "Brackets revealed Sunday before games start." Post-Selection-Sunday it becomes the live draft board powered by `docs/players.json`.
- **`{Year} Summary`** (one per archived year) — historical recap, with sub-tabs (see below).
- **`{Year} Draft`** (per archived year, internally `kind=redraft`) — loads that year's archived projections into the live draft board so you can run a mock or live draft against historical values. Resets any in-progress current draft state.

Tabs are generated dynamically from `docs/archive/index.json`. Adding a new archived year is just: snapshot → analyze → `build_archive_json.py YEAR` → bump `SELECTION_SUNDAY`.

### History Summary sub-tabs

| Tab | What it shows |
|---|---|
| **Standings** | Final entry leaderboard with per-round point breakdown, sparkline bars |
| **Draft Replay** | Every pick in order, sortable, filterable by entry. Color-coded vs projection. Banner at top listing all in-tournament injuries. |
| **Top Performers** | Top 50 players by actual points (regardless of draft position) |
| **Steals & Busts** | Top 15 each by residual (actual − projected). Excludes injuries. |
| **Pick Value** | Model-independent: top 20 risers and fallers by `draft_pick − actual_rank` |
| **Bracket** | Final Four + Championship card on top, then 4 region trees (R64→E8) with team logos, seeds, scores |
| **Awards** | League-Wide card on top (8 awards across all entries), then per-entry cards: Best Pick, Worst Pick, Best Value (slot riser), Worst Value (slot faller), Best Team, Worst Team, Best Seed, Worst Seed. Best/Worst Team and Seed only display when the average residual sign matches the label. |
| **Algorithm** | Top-N calibration, bias by seed, draft efficiency (actual vs algo-following vs rank-baseline), entry post-mortem (MAE, hit rate) |

### Polish features
- **Team logos**: every team name is iconified via ESPN's CDN. The team-id map is fetched from `docs/team_logos.json` (single-sourced from `src/scrape_players_espn.py` via `build_team_logos.py`), with an inline copy in `index.html` as first-paint fallback.
- **In-tournament injury indicators**: confirmed injuries get a red `🤕 INJ` tag inline, a faint red row tint, and appear in a banner at the top of Draft Replay. Excluded from Steals/Busts, Awards, and all calibration aggregates.
- **URL hash routing**: `#year=2026&kind=summary&section=bracket` deep-links to a specific tab + section. Sharing/bookmarking works. Browser back/forward via `hashchange`.
- **Keyboard shortcuts**: <kbd>←</kbd>/<kbd>→</kbd> cycle year tabs; <kbd>1</kbd>–<kbd>8</kbd> switch sub-tabs (in summary view).
- **Browser tab title** updates per state (e.g., `2026 Summary · Bracket · MM Player Tourney`).
- **Sticky sub-tab bar** so navigation doesn't scroll away on long pages.
- **Tabular numerals** site-wide for clean number columns.
- **Mobile responsive** — tabs, header, and tables all adapt to small screens.
- **Service worker** caches static assets, players.json, and `archive/*.json` for offline access. `CACHE_NAME` versioning evicts stale caches on updates.

### Live draft board
- **Live Draft mode** — real-time draft tracking with turn awareness, snake/linear, custom team names. Shows "YOUR PICK!" on your turn.
- **Mock Draft mode** — simulates other teams auto-picking best available.
- **Free Draft mode** — no turn tracking, just mark Us/Them as picks happen.
- **Filters**: search by player/team, seed range (min/max), region, hide-drafted toggle, favorites
- **Conflict warnings** if your roster has bracket conflicts (two players who would meet)
- **Export**: CSV download of your draft or the full player database
- **Persistence**: everything saves to `localStorage` and survives refresh

---

## Yearly archive system

Each draft year is frozen under `archive/<year>/` so the algorithm can be improved across seasons without losing prior context. When the model changes, archived projections stay untouched — so you can always re-measure how an old version performed.

### Why it matters
Without archives, every algorithm change is unfalsifiable. With them you can answer: "Did my new injury model actually reduce error, or did I just tune to noise?" One year is a sample size of 1 — meaningful pattern recognition needs at least 3 years of frozen data to compare against.

### Archive layout
```
archive/<year>/
├── algorithm_version.txt       # git SHA, methodology notes, post-mortem summary
├── projections_final.csv       # frozen pre-draft projection (DO NOT MODIFY)
├── inputs/                     # frozen pipeline inputs:
│   ├── kenpom.csv, kenpom_raw.txt, kenpom_tournament.csv
│   ├── injuries.csv, injury_overrides.csv
│   ├── bracket.json
│   ├── all_player_stats.csv
│   ├── player_stats/           # per-team JSON cache
│   └── insights.json           # pre-draft scouting notes
├── actual/                     # post-tournament:
│   ├── player_results.csv      # round-by-round actual + alive + in_tournament_injury
│   ├── draft_picks.csv         # full draft order with espn_ids
│   ├── entry_totals.csv        # per-entry round totals + final standings
│   ├── bracket_outcome.json    # round-by-round survivors + games[] with scores
│   └── injury_candidates.csv   # output of detect_injuries.py for review
└── analysis/                   # generated post-mortem CSVs:
    ├── player_residuals.csv, calibration.csv
    ├── bias_by_seed.csv, bias_by_injury.csv
    ├── team_round_vs_projection.csv
    ├── draft_value.csv, draft_efficiency.csv
    └── entry_post_mortem.csv
```

### Schema validation
`src/archive_schema.py` declares the canonical field names for `player_results.csv`, `draft_picks.csv`, `entry_totals.csv`, and `bracket_outcome.json`. When you run `build_archive_json.py`, it validates CSV headers (catches column-rename breakage) and bracket structure (must have 63 games with consistent advancement). Warnings print to stdout if anything's wrong. **All validators currently pass on 2026.**

### Player aliases
`data/player_aliases.csv` records known name variants between league spreadsheets and the project's canonical names (e.g., `Patrick Ngongba` → `Patrick Ngongba II`, `UConn` → `Connecticut`). Append new normalizations here so future ingests don't repeat the work.

---

## Dependencies
```
pip install pandas requests beautifulsoup4
```
Also needs Python ≥ 3.9 (for `dict[str, ...]` type hints in `archive_schema.py`).

## Key Design Decisions

1. **Expected value over ceiling** — Rankings optimize for the most likely total points, not upside. This is correct for a 14-player roster where the law of large numbers applies.
2. **Team quality over seed labels** — We use actual KenPom ratings, not historical seed-line averages. A strong 4-seed and a weak 4-seed get different expected games.
3. **Recent form is the only "extra" modifier** — After testing tournament surge, scoring concentration, and blowout reduction against historical data, only recent form (60/40 blend) survived.
4. **Injuries are first-class** — Both team-level (AdjO reduction for OUT players) and player-level (`games_missed` + `fitness_mult`).
5. **Per-round scoring** — Not flat PPG × games. Each round has different opponents with different defensive quality and pace.
6. **Frozen archives** — Algorithm changes never overwrite historical projections. The whole point of `archive/<year>/` is that it's append-only and immutable per year.
7. **Single source of truth for shared data** — ESPN team IDs live in one Python dict (`scrape_players_espn.ESPN_TEAM_IDS`) and are exported to the website via `build_team_logos.py`. Archive CSV field names live in `archive_schema.py`. No duplication, no silent drift.
