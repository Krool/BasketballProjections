# March Madness 2026 - Fantasy Draft Projections

Fantasy draft board for March Madness player pools. Projects which players will score the most total points across the NCAA tournament based on KenPom efficiency ratings, recent form, and injury data.

**Live draft board**: [krool.github.io/BasketballProjections](https://krool.github.io/BasketballProjections/) or open `docs/index.html` locally.

## How to Reuse This for Next Year

### 1. Update KenPom data
After the bracket is announced (Selection Sunday):
1. Go to [kenpom.com](https://kenpom.com) and copy the ratings table
2. Paste into `data/kenpom_raw.txt`
3. Run `python src/parse_kenpom.py` — generates `kenpom.csv` and `kenpom_tournament.csv`
4. Verify `kenpom_tournament.csv` has all 68 tournament teams with correct seeds

### 2. Update the bracket
Edit `data/bracket.json` with the 64-team bracket. Structure:
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
Team names must match KenPom exactly (e.g., "Iowa St." not "Iowa State").

### 3. Update ESPN team IDs
In `src/scrape_players_espn.py`, update the `ESPN_TEAM_IDS` dict for any new tournament teams. These are the numeric IDs from ESPN URLs (e.g., `espn.com/mens-college-basketball/team/stats/_/id/150` → Duke = 150).

### 4. Update First Four matchups
In `src/update_first_four.py`, update the `FIRST_FOUR` list with the new play-in matchups.

In `src/main.py`, update the `FIRST_FOUR_PAIRS` list for undecided matchups (both teams' players appear in projections until the game is played).

### 5. Update injury data
Edit `data/injury_overrides.csv`:
```csv
player,team,status,notes
Player Name,Team Name,OUT,Description of injury
```
Status values: `OUT`, `DAY-TO-DAY`, `PROBABLE`, `RETURNING`, `HEALTHY`

### 6. Clear caches and regenerate
```bash
rm -rf data/player_stats/          # ESPN player stat cache
rm -f data/all_player_stats.csv    # Combined stats
rm -f data/player_stats/_recent_form.json  # Game log cache
python src/main.py                 # Full pipeline
```

### 7. Update insights (optional)
Edit `docs/insights.json` with scouting notes per player:
```json
{
  "Player Name": "Note about this player for the draft board tooltip"
}
```

## Pipeline Steps (src/main.py)

The pipeline runs 7 steps:

1. **Load KenPom data** — Team ratings (AdjO, AdjD, AdjT) from `kenpom_tournament.csv`
2. **Load bracket** — 64-team bracket from `bracket.json`
3. **Load/scrape player stats** — Per-player PPG, RPG, APG from ESPN. Cached in `data/player_stats/`. Also captures ESPN player IDs for game log scraping and team logos.
4. **Load injuries** — Manual overrides from `injury_overrides.csv` + ESPN scrape (unreliable). Manual overrides take precedence.
5. **Adjust KenPom + simulate bracket** — Reduce AdjO for teams with OUT players, then propagate win probabilities through the bracket tree to compute expected games per team. Also computes per-round opponent context (DRtg, AdjT, margin) for matchup adjustments.
6. **Scrape recent form** — Game logs from ESPN for players with 12+ PPG. Computes last-5-game average. Cached in `_recent_form.json`.
7. **Project points** — Combine all data into final projections. Deploy to `docs/players.json`.

## Projection Model

### Formula
```
projected_points = Σ (P(play round r) × adjusted_PPG_r)
adjusted_PPG = blended_PPG × pace_factor × defense_factor × injury_multiplier
```

### Factors

**Win probability** (expected games):
```
P(A beats B) = 1 / (1 + 10^(-margin / 20))
margin = (AdjO_A - AdjD_A) - (AdjO_B - AdjD_B)
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
Scales scoring by opponent quality. Range: ~±11%. Opponents are probability-weighted.

**Injury multipliers** (player level):
| Status | Multiplier | Use When |
|---|---|---|
| HEALTHY | 1.0 | Default |
| PROBABLE | 0.9 | Expected to play, minor issue |
| RETURNING | 0.8 | Back from injury, may have rust |
| DAY-TO-DAY | 0.7 | Truly uncertain |
| OUT | 0.0 | Not playing |

**Injury-adjusted KenPom** (team level):
```
loss_rate = 0.35 + (0.10 if player_ppg >= 20)
AdjO_reduction = (ppg × loss_rate / team_total_ppg) × (AdjO - 107)
```
Only applied for OUT players. Reduces team's offensive efficiency before bracket simulation.

### What we tested and removed
These factors were implemented, tested against historical data, and removed because they either had no evidence or didn't change draft rankings:
- **Tournament scoring surge** (+8% for stars) — Only supported by survivorship-biased data. Sensitivity test: changed 0 picks in top 30.
- **Scoring concentration** (boost go-to scorers) — Historical data showed no effect (high-share players surged 1.18x vs low-share 1.22x).
- **Blowout minutes reduction** — Historical data showed the opposite: stars score MORE in blowouts (Edey 30pts in R1, Clingan 19 in 20min).

## Draft Board Features (docs/index.html)

### Draft Modes
- **Live Draft** — Real-time draft tracking with turn awareness. Setup: teams, rounds, your position, snake/linear, custom team names. Shows "YOUR PICK!" when it's your turn, hides irrelevant buttons. Blocks picks after completion.
- **Mock Draft** — Simulates other teams auto-picking best available. Configurable speed and draft type.
- **Free Draft** — No turn tracking, just mark Us/Them as picks happen.

### UI Features
- School logos from ESPN CDN (`a.espncdn.com/i/teamlogos/ncaa/500/{id}.png`)
- Best Available banner with quick-draft button on your turn
- Seed range filter (min/max dropdowns, default 1-16)
- Search by player or team name
- Favorites system (star players you're targeting)
- Conflict warnings (bracket conflicts between your players)
- Sortable columns
- Mobile responsive (hides columns, compact layout)

### Draft Log
- Shows pick number, round, team name (from setup), school logo
- Your picks highlighted in purple
- Snake/linear order calculated from draft config

### Draft Summary (after completion)
- Logo cloud: school logos sized by their % of your total projected points
- Player breakdown grouped by school team
- League standings: all draft teams ranked by projected points with conflict penalties

### Export
- **Export Draft**: CSV with pick #, round, draft team name, player stats
- **Export All**: Full player database with drafted/available status

### Persistence
Everything saves to localStorage: drafted players, your team, favorites, draft order, draft config, team names, live draft state. Survives page refresh.

## Yearly Archive & Post-Mortem

Each draft year is frozen under `archive/<year>/` so the algorithm can be improved across seasons without losing prior context. When the model changes, archived projections stay untouched — so you can always re-measure how an old version performed.

### Workflow

**Before draft day** (snapshot the inputs you're about to draft on):
```bash
python src/snapshot_year.py 2027 --notes "tweaked surge factor"
```
Copies `data/kenpom.csv`, `data/injuries_combined.csv`, `data/bracket.json`, and `output/projections.csv` into `archive/2027/`. Records the git SHA so you know which algorithm version produced the projections.

**After the tournament** (ingest results and analyze):
1. Paste actual results into the conversation; Claude writes them to `archive/2027/actual/player_results.csv`, `draft_picks.csv`, `entry_totals.csv`, `bracket_outcome.json`.
2. `python src/detect_injuries.py 2027` — flags ~2-5 players whose data smells like an in-tournament injury. Glance at the list, confirm real ones.
3. Manually populate the `in_tournament_injury` column for confirmed cases (so they're excluded from algorithm calibration).
4. `python src/analyze_year.py 2027` — produces residuals, calibration, bias-by-seed, draft value, and biggest misses, all written to `archive/2027/analysis/`.
5. `python src/compare_years.py` — once 2+ years exist, tracks calibration trends across seasons.

### Archive layout
```
archive/<year>/
  algorithm_version.txt   # git SHA + methodology notes for the algo that produced these projections
  projections_final.csv   # frozen pre-draft projection (do not modify)
  inputs/                 # frozen kenpom, injuries, bracket
  actual/                 # post-tournament: player_results, draft_picks, entry_totals, bracket_outcome, injury_candidates
  analysis/               # generated post-mortem CSVs
```

### Why this matters
Without archives, every algorithm change is unfalsifiable. With them you can answer: "Did my new injury model actually reduce error, or did I just tune to noise?" One year is a sample size of 1 — meaningful pattern recognition needs at least 3 years of frozen data to compare against.

See `docs/post_tournament_workflow.md` for the full step-by-step.

## Project Structure
```
data/
  bracket.json              # 64-team bracket
  injury_overrides.csv      # Manual injury statuses (authoritative source)
  injuries_combined.csv     # Generated: merged ESPN + manual
  kenpom_raw.txt            # Raw KenPom paste (not committed)
  kenpom.csv                # All 365 D1 teams
  kenpom_tournament.csv     # 68 tournament teams with seeds
  all_player_stats.csv      # Player stats with ESPN IDs
  player_stats/             # Per-team JSON cache + _recent_form.json

src/
  main.py                   # Pipeline orchestrator (7 steps)
  parse_kenpom.py           # Raw KenPom → CSV
  simulate_bracket.py       # Win probability + bracket propagation + round context
  scrape_players_espn.py    # ESPN scraper (stats + game logs + IDs)
  scrape_injuries.py        # Injury loader (manual + ESPN)
  project_points.py         # PPG × expected_games with adjustments
  update_first_four.py      # Update bracket with play-in results
  snapshot_year.py          # Freeze data/ + output/ into archive/<year>/ before draft day
  detect_injuries.py        # Heuristic scanner for in-tournament injury candidates
  analyze_year.py           # Post-mortem: residuals, calibration, bias, draft value, draft efficiency
  compare_years.py          # Cross-year algorithm performance trends
  build_archive_json.py     # Convert archive/<year>/ → docs/archive/<year>.json for the SPA

archive/
  <year>/
    algorithm_version.txt   # git SHA + methodology notes
    projections_final.csv   # frozen pre-draft projections
    inputs/                 # frozen kenpom, injuries, bracket
    actual/                 # post-tournament results + injury flags
    analysis/               # post-mortem CSVs

output/
  projections.csv           # Final ranked projections

docs/
  index.html                # SPA — Draft Mode + History Mode + countdown landing
  players.json              # Live projections (auto-updated by main.py)
  insights.json             # Manual scouting notes
  archive/
    index.json              # List of archived years
    <year>.json             # Bundled post-mortem data for History Mode
    <year>_players.json     # players.json-shaped file for "Re-Draft year X" feature
  sw.js                     # Service worker (network-first for data)
  manifest.json             # PWA manifest
  icon-192.png, icon-512.png
```

## Website modes

The SPA at `docs/index.html` has two modes, switchable from the header:

- **📋 Draft Mode** — the live draft board (loads `players.json`). Off-season (before Selection Sunday) it shows a countdown clock instead, with buttons to view the 2026 recap or load 2026 projections into the board for a replay draft.
- **📊 History Mode** — archive viewer for past seasons. Year selector + tabs for standings, draft replay, top performers, steals & busts, bracket, and algorithm post-mortem.

The "↻ 2026" button (live draft controls) and "Re-Draft 2026" CTA (countdown view) both call `loadArchiveDraft(2026)` which swaps the players array with the archived projections so the existing draft UI works against historical data.

## Dependencies
```
pip install pandas requests beautifulsoup4 PyPDF2
```
PyPDF2 is optional (only used for reading competitor ranking PDFs).

## Key Design Decisions

1. **Expected value over ceiling** — Rankings optimize for the most likely total points, not upside. This is correct for a 14-player roster where the law of large numbers applies.

2. **Team quality over seed labels** — We use actual KenPom ratings, not historical seed-line averages. A strong 4-seed and a weak 4-seed get different expected games.

3. **Recent form is the only "extra" modifier** — After testing tournament surge, scoring concentration, and blowout reduction against historical data, only recent form (60/40 blend) survived. It's the only modifier that actually changes draft rankings.

4. **Injuries are first-class** — Both team-level (AdjO reduction for OUT players) and player-level (multipliers). Boyd's Bets, our main competitor, doesn't adjust for injuries at all — their top 50 includes 4 OUT players.

5. **Per-round scoring** — Not flat PPG × games. Each round has different opponents with different defensive quality and pace. A player facing Siena in R1 scores differently than facing Michigan in E8.
