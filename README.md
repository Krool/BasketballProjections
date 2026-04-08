# March Madness Player Tourney

Fantasy draft board and historical recap for March Madness player pools. Projects which players will score the most total points across the NCAA tournament based on KenPom efficiency ratings, recent form, and injury data. After each tournament, archives the projections + actuals for cross-year algorithm post-mortem analysis.

**Live site**: [krool.github.io/BasketballProjections](https://krool.github.io/BasketballProjections/) or open `docs/index.html` locally.

The site has three kinds of tabs in the header — see [Website](#website-docsindexhtml) below.

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
Copies all projection inputs (kenpom.csv + raw + tournament filter, injuries_combined + injury_overrides, bracket.json, all_player_stats.csv, the per-team `data/player_stats/` cache, and `docs/insights.json`) plus `output/projections.csv` into `archive/2027/`. Records the git SHA + commit message so you know which algorithm version produced the projections.

**After the tournament** (ingest results, detect injuries, analyze, build website JSON):
1. Paste actual results into the conversation; Claude writes them to `archive/2027/actual/player_results.csv`, `draft_picks.csv`, `entry_totals.csv`, `bracket_outcome.json`. **IMPORTANT**: verify the champion against an external source (Wikipedia / NCAA) before trusting league-spreadsheet `alive=1` flags — in 2026 the spreadsheet's `alive` column was wrong and required a manual correction.
2. `python src/detect_injuries.py 2027` — flags ~2-5 players whose data smells like an in-tournament injury (signals: DNP, sustained zero-cliff, massive underperformance vs projection). Glance at the list, confirm real ones.
3. Manually populate the `in_tournament_injury` column in `player_results.csv` for confirmed cases. They get excluded from algorithm calibration AND get a 🤕 INJ tag in the website's history view.
4. `python src/analyze_year.py 2027` — produces residuals, calibration, bias-by-seed, draft value, draft efficiency, entry post-mortem.
5. `python src/build_archive_json.py 2027` — converts archive CSVs into bundled JSON for the website (`docs/archive/2027.json` + `2027_players.json` for the Re-Draft feature). Updates `docs/archive/index.json`.
6. `python src/compare_years.py` — once 2+ years exist, tracks calibration trends across seasons.
7. Bump `SELECTION_SUNDAY` constant in `docs/index.html` to next year's date so the upcoming-year tab labels and countdown work.

### Archive layout
```
archive/<year>/
  algorithm_version.txt   # git SHA + methodology notes for the algo that produced these projections
  projections_final.csv   # frozen pre-draft projection (DO NOT MODIFY)
  inputs/                 # frozen pipeline inputs:
    kenpom.csv, kenpom_raw.txt, kenpom_tournament.csv
    injuries.csv (was injuries_combined), injury_overrides.csv
    bracket.json
    all_player_stats.csv
    player_stats/         # per-team JSON cache
    insights.json         # pre-draft scouting notes
  actual/                 # post-tournament:
    player_results.csv    # round-by-round actual + alive + in_tournament_injury
    draft_picks.csv       # full draft order with espn_ids
    entry_totals.csv      # per-entry round totals + final standings
    bracket_outcome.json  # round-by-round survivors + games[] with scores
    injury_candidates.csv # output of detect_injuries.py for review
  analysis/               # generated post-mortem CSVs:
    player_residuals.csv, calibration.csv, bias_by_seed.csv,
    bias_by_injury.csv, team_round_vs_projection.csv,
    draft_value.csv, draft_efficiency.csv, entry_post_mortem.csv
```

### Why this matters
Without archives, every algorithm change is unfalsifiable. With them you can answer: "Did my new injury model actually reduce error, or did I just tune to noise?" One year is a sample size of 1 — meaningful pattern recognition needs at least 3 years of frozen data to compare against.

See `docs/post_tournament_workflow.md` for the full step-by-step.

### Player aliases
`data/player_aliases.csv` records known name variants between league spreadsheets and the project's canonical names (e.g., `Patrick Ngongba` → `Patrick Ngongba II`, `UConn` → `Connecticut`). New normalizations should be appended here so future ingests don't repeat the work.

### Known data gaps (2026)
- **RJ Johnson (Kennesaw St.)** — drafted in 2026 but missing from the ESPN player scrape entirely. Cannot be joined to projections. Investigate `src/scrape_players_espn.py` before 2027 to ensure all rostered players are captured.
- **The original "alive" column** in the league spreadsheet had UConn marked as the survivor when Michigan actually won. Verify externally on ingest.

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

## Website (`docs/index.html`)

Single SPA with three kinds of tabs in the header:

- **{Year} Draft** (e.g., `2027 Draft`) — the upcoming season. Pre-Selection-Sunday shows a countdown clock + a Re-Draft CTA. Post-Selection-Sunday it becomes the live draft board powered by `players.json`.
- **{Year} Summary** (one per archived year, e.g., `2026 Summary`) — the History view. Sub-tabs: **Standings**, **Draft Replay**, **Top Performers**, **Steals & Busts**, **Pick Value**, **Bracket**, **Awards**, **Algorithm**.
- **{Year} Redraft** (one per archived year) — loads that year's archived projections into the live draft board so you can run a mock or live draft against historical values. Resets any in-progress current draft state.

Tabs are generated dynamically from `docs/archive/index.json`. Adding a new year is just: snapshot → analyze → `build_archive_json.py YEAR` → bump `SELECTION_SUNDAY` constant.

### History view sub-tabs

| Tab | What it shows |
|---|---|
| **Standings** | Final entry leaderboard with per-round point breakdown |
| **Draft Replay** | Every pick in order, sortable, filterable by entry. Color-coded vs projection. Includes a banner listing all in-tournament injuries. |
| **Top Performers** | Top 50 players by actual points (regardless of draft position) |
| **Steals & Busts** | Top 15 each by residual (excludes injuries) |
| **Pick Value** | Model-independent: top 20 risers and fallers by `draft_pick − actual_rank` |
| **Bracket** | Full 4-region visual bracket with logos, seeds, scores, plus Final Four + Championship card |
| **Awards** | 8 per-entry awards: Best Pick, Worst Pick, Best Value (riser), Worst Value (faller), Best Team, Worst Team, Best Seed, Worst Seed. Best/Worst Team and Seed only display when the average residual matches the label (no negative "best"). |
| **Algorithm** | Top-N calibration, bias by seed, draft efficiency (actual vs algo-following vs rank-baseline), entry post-mortem (MAE, hit rate) |

### Visual details
- **Team logos**: every team name in History view is iconified via ESPN's CDN (`a.espncdn.com/i/teamlogos/ncaa/500/<id>.png`). The team-id map lives in `docs/index.html` as `TEAM_LOGO_IDS` and is kept in sync with `src/scrape_players_espn.py`.
- **Injury indicators**: confirmed in-tournament injuries get a red `🤕 INJ` tag inline, a faint red row tint, and appear in a banner at the top of Draft Replay. They are excluded from Steals/Busts, Awards calculations, and all calibration aggregates.
- **Countdown landing** (Draft tab off-season): live ticking clock to next Selection Sunday + a Re-Draft button.

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
