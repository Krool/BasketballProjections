# March Madness 2026 - Fantasy Draft Projections

Fantasy draft board for a 20-team league where each team drafts 14 players (280 total picks). Projects which players will score the most total points across the 2026 NCAA tournament.

**Live draft board**: Open `docs/index.html` or deploy to GitHub Pages.

## Projection Methodology

### Core Formula

For each player, we compute expected points **per tournament round**, then sum across all 6 possible rounds:

```
projected_points = Σ (P(play round r) × adjusted_PPG_r)
```

Where for each round:
```
adjusted_PPG = PPG × surge × pace_factor × defense_factor × blowout_factor × injury_mult
```

### Factor Breakdown

#### 1. Win Probability Model
Teams' chances of advancing are computed analytically (not Monte Carlo) using KenPom adjusted efficiency ratings:

```
P(A beats B) = 1 / (1 + 10^(-margin / 17))
margin = (AdjO_A - AdjD_A) - (AdjO_B - AdjD_B)
```

The divisor of **17** is calibrated against historical single-elimination upset rates:
- 1-seeds win R1: ~99% (model: 99.6%)
- 5v12 upset rate: ~35% (model: ~13-17% depending on matchup)
- 8v9 matchups: ~50/50 (model: ~60-65% for higher seed)
- Best team championship odds: ~15-25% (model: ~28% for Duke)

Each team's probability of playing each round is derived by propagating win probabilities through the full bracket tree.

#### 2. Tournament Scoring Surge
Historical analysis (2015-2025) shows star players score significantly more in March Madness than their regular season average. The top tournament scorer averaged **+36% above regular season PPG** — driven by tighter rotations, higher usage, and elevated intensity.

We apply a conservative, tiered bump (the +36% is survivorship-biased since we only see players whose teams went deep):

| Regular Season PPG | Surge Factor | Rationale |
|---|---|---|
| 20+ PPG | 1.08 (+8%) | Stars get more touches, tighter rotation |
| 15-20 PPG | 1.04 (+4%) | Solid starters see slight usage increase |
| Under 15 PPG | 1.00 (none) | Role players don't meaningfully surge |

#### 3. Pace Normalization
A player's PPG was earned at their team's season tempo (AdjT). In any given tournament game, the actual pace is the average of both teams' tempos:

```
pace_factor = ((team_AdjT + opponent_AdjT) / 2) / team_AdjT
```

This adjusts for tempo mismatches — e.g., a player on Alabama (73.1 tempo) facing Houston (63.3 tempo) will play at ~68.2 possessions, producing ~93% of their normal scoring rate.

#### 4. Opponent Defense Adjustment
Per-round scoring is scaled by the weighted-average defensive efficiency of likely opponents vs the D-I average (100.0):

```
defense_factor = opponent_DRtg / 100.0
```

A player facing Siena (DRtg 109) scores ~9% more than average. Against Michigan (DRtg 89), ~11% less. Opponents in later rounds are probability-weighted across all teams that could reach that round.

#### 5. Blowout Minutes Reduction
In lopsided games, starters sit early. Historical data (e.g., Edey scored 30 in 23 min vs a 16-seed in 2024) shows stars still produce at ~80% even in blowouts:

```
blowout_factor = max(0.80, 1.0 - (|margin| - 7) * 0.006)
```

| Expected Margin | Factor | Interpretation |
|---|---|---|
| ≤ 7 pts | 1.00 | Competitive game, full minutes |
| 17 pts | 0.94 | Moderate win, slight rest |
| 27 pts | 0.88 | Clear blowout, starters sit ~5 min early |
| 40+ pts | 0.80 | Floor — stars still produce in limited time |

Uses absolute margin — underdogs in blowout losses also see reduced minutes.

#### 6. Injury-Adjusted KenPom (Team Level)
Teams with OUT players have their KenPom offensive efficiency (AdjO) reduced before bracket simulation:

```
loss_rate = 0.35 + (0.10 if player_ppg >= 20)
net_loss = player_ppg × loss_rate
AdjO_reduction = (net_loss / team_total_ppg) × (team_AdjO - 107)
```

This reflects that ~65% of a missing player's production is backfilled by teammates at lower efficiency. Stars (20+ PPG) are harder to replace.

#### 7. Injury Multipliers (Player Level)

| Status | Multiplier | Use When |
|---|---|---|
| HEALTHY | 1.0 | Default — no injury concerns |
| PROBABLE | 0.9 | Expected to play, minor lingering issue |
| RETURNING | 0.8 | Back from injury, may have limited minutes / rust |
| DAY-TO-DAY | 0.7 | Truly uncertain — missed recent games, status unknown |
| OUT | 0.0 | Season-ending or ruled out |

### Historical Calibration

Top tournament scorers 2015-2025 (for context — our projections are expected values, which are lower than actuals because actuals are conditional on the team going deep):

| Year | #1 Scorer | Total Pts | Seed | Tournament PPG |
|---|---|---|---|---|
| 2025 | Walter Clayton Jr. | 123 | 1 | 24.6 |
| 2024 | Zach Edey | 177 | 1 | 29.5 |
| 2023 | Adama Sanogo | 118 | 4 | 19.7 |
| 2022 | Caleb Love | 113 | 8 | 18.8 |
| 2021 | Johnny Juzang | 137 | 11 | 27.4 |
| 2019 | Carsen Edwards | 139 | 3 | 34.8 |

Average #1 scorer: **124 pts**. Championship teams typically place **3-5 players** in the top 10 scorers.

## Quick Start

```bash
pip install pandas requests beautifulsoup4

# Run the full pipeline (generates projections + deploys to docs/)
python src/main.py
```

## Draft Day Workflow

### Before the draft (after First Four, before Round of 64)

The First Four play-in games (March 17-18) do NOT count for fantasy scoring. By draft time, those games will be done. Update the bracket with results:

```bash
# Interactive — prompts for each winner
python src/update_first_four.py

# Or pass results directly
python src/update_first_four.py --west11 "Texas" --mw16 "Howard" --mw11 "SMU" --south16 "Lehigh"
```

First Four matchups:
| Slot | Matchup | Winner plays |
|------|---------|-------------|
| West 11 | N.C. State vs Texas | BYU (R64) |
| Midwest 16 | UMBC vs Howard | Michigan (R64) |
| Midwest 11 | SMU vs Miami (OH) | Tennessee (R64) |
| South 16 | Lehigh vs Prairie View A&M | Florida (R64) |

If a new team enters the bracket (e.g. Texas replaces N.C. State):
1. Add their KenPom ratings to `data/kenpom_tournament.csv`
2. Delete their cache in `data/player_stats/` if it exists
3. Re-run `python src/main.py` — it will scrape missing team stats automatically

### Last-minute injury updates

Edit `data/injury_overrides.csv` and re-run `python src/main.py`.

Name matching is fuzzy on suffixes (Jr., Sr., II, III) — "Patrick Ngongba II" matches "Patrick Ngongba".

### During the draft

Open `docs/index.html` in a browser. Features:
- Click **Draft** to mark players as taken (persists via localStorage)
- **Best Available** banner shows the top undrafted player
- Filter by team, seed, or search by name
- **Favorites** to star players you're targeting
- **Draft Log** sidebar tracks pick order
- **Mock Draft** mode simulates other teams picking
- **Export** downloads draft results as CSV
- **Undo** / **Reset** for mistakes

## Project Structure

```
data/
  bracket.json             # 64-team bracket (edit after First Four)
  injury_overrides.csv     # Manual injury statuses (primary injury source)
  injuries_combined.csv    # Generated: merged ESPN + manual injuries
  kenpom_raw.txt           # Raw KenPom ratings (paste from kenpom.com)
  kenpom.csv               # Parsed: all 365 D1 teams
  kenpom_tournament.csv    # Parsed: 68 tournament teams with seeds
  all_player_stats.csv     # Combined player stats from ESPN
  player_stats/            # Per-team JSON cache from ESPN scraping

src/
  main.py                  # Full pipeline — run this to regenerate everything
  update_first_four.py     # Update bracket with play-in results
  parse_kenpom.py          # Parse raw KenPom data into CSVs
  simulate_bracket.py      # Analytical bracket simulation (expected games)
  scrape_players_espn.py   # Scrape player per-game stats from ESPN
  scrape_injuries.py       # Load injuries (manual overrides + ESPN)
  project_points.py        # Combine data into final projections

output/
  projections.csv          # Final ranked player projections

docs/
  index.html               # Draft board web app
  players.json             # Deployed projections (auto-updated by main.py)
  insights.json            # Manual scouting notes per player
```

## Updating Data

**KenPom ratings**: Paste updated table into `data/kenpom_raw.txt`, then run `python src/parse_kenpom.py`.

**Bracket changes**: Edit `data/bracket.json`. Team names must match KenPom exactly.

**Injuries**: Edit `data/injury_overrides.csv`. Re-run `python src/main.py`.

**Re-scrape all player stats**: Delete `data/player_stats/` and `data/all_player_stats.csv`, then re-run `python src/main.py`.
