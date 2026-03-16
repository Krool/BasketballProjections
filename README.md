# March Madness 2026 - Fantasy Draft Projections

Fantasy draft board for a 20-team league where each team drafts 14 players (280 total picks). Projects which players will score the most total points across the 2026 NCAA tournament.

**Live draft board**: Open `docs/index.html` or deploy to GitHub Pages.

## How It Works

```
projected_points = PPG × expected_games × injury_multiplier
```

- **PPG**: Season per-game scoring average (scraped from ESPN)
- **Expected games**: Analytically simulated from KenPom adjusted efficiency ratings and the actual bracket matchups — probability propagation, not Monte Carlo
- **Injury multiplier**: OUT = 0.0, DAY-TO-DAY = 0.7, RETURNING = 0.8, HEALTHY = 1.0

Win probability formula: `P(A beats B) = 1 / (1 + 10^(-margin / 11))` where margin is the KenPom net rating difference.

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

Status values and their effect:
| Status | Multiplier | Use when |
|--------|-----------|----------|
| HEALTHY | 1.0 | Default — no injury concerns |
| RETURNING | 0.8 | Was injured, confirmed playing (slight discount for rust/minutes) |
| DAY-TO-DAY | 0.7 | Uncertain — may or may not play |
| OUT | 0.0 | Season-ending or ruled out |

Name matching is fuzzy on suffixes (Jr., Sr., II, III) — "Patrick Ngongba II" matches "Patrick Ngongba".

### During the draft

Open `docs/index.html` in a browser. Features:
- Click **Draft** to mark players as taken (persists via localStorage)
- **Best Available** banner shows the top undrafted player
- Filter by team, seed, or search by name
- **Clear Filters** resets all filters
- **Favorites** to star players you're targeting
- **Draft Log** sidebar tracks pick order
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
  players.json             # JSON version (same data)

docs/
  index.html               # Draft board web app
  players.json             # Deployed projections (auto-updated by main.py)
```

## Updating Data

**KenPom ratings**: Paste updated table into `data/kenpom_raw.txt`, then run `python src/parse_kenpom.py`.

**Bracket changes**: Edit `data/bracket.json`. Team names must match KenPom exactly.

**Injuries**: Edit `data/injury_overrides.csv`. Re-run `python src/main.py`.

**Re-scrape all player stats**: Delete `data/player_stats/` and `data/all_player_stats.csv`, then re-run `python src/main.py`.

**Add a missing player manually**: Append a row to `data/all_player_stats.csv` with columns: `player,team,games_played,mpg,ppg,rpg,apg`.

## Known Limitations

- **Cal Baptist** (13-seed) is missing from player stats — ESPN scrape failed for this team. Low impact since 13-seeds rarely get drafted.
- **First Four teams** are pre-filled in the bracket with one team per slot. After play-in results, use `update_first_four.py` to swap in the actual winners.
- **Injury multipliers are coarse**: RETURNING gets full credit (1.0) even for players playing through nagging injuries (e.g. Philon's thigh/groin, Acuff's ankle). Use your judgment for tiebreakers.
- **No pace/style adjustment**: A player on a fast-paced team in a slow-paced matchup might score less than projected. The model only uses PPG and expected games.

## Current Injury Report (as of 3/16/2026)

### OUT (season-ending)
| Player | Team | Injury |
|--------|------|--------|
| Caleb Foster | Duke | Fractured foot — surgery, out foreseeable future |
| Braden Huff | Gonzaga | Left knee since Jan 15 — ruled out first weekend |
| Richie Saunders | BYU | ACL tear Feb 14 |
| JT Toppin | Texas Tech | ACL tear Feb 17 |
| Carter Welling | Clemson | ACL tear in ACC tournament |
| L.J. Cason | Michigan | ACL tear late Feb |
| Matt Hodge | Villanova | ACL tear |
| Caleb Wilson | North Carolina | Fractured hand + thumb |
| Jayden Quaintance | Kentucky | Knee — played only 4 games |
| Dawson Baker | BYU | ACL + MCL/PCL |

### DAY-TO-DAY (0.7x multiplier — uncertain)
| Player | Team | PPG | Notes |
|--------|------|-----|-------|
| Patrick Ngongba II | Duke | 10.7 | Foot soreness — Scheyer optimistic for Thursday |
| Mikel Brown Jr. | Louisville | 18.2 | Back — missed ACC tourney, slowly progressing |
| Labaron Philon | Alabama | 21.7 | Thigh/groin all season — playing but not 100% |
| Jaylin Stewart | Connecticut | 4.5 | Knee inflammation — "it'll be close" for R1 |
| Silas Demary Jr. | Connecticut | 10.9 | Ankle sprain Big East final — mild, no swelling |
| Corey Washington | SMU | 11.3 | Shoulder in ACC tourney — status unknown |
| John Bol | UCF | 6.0 | Collapsed in Big 12 tourney — no diagnosis |

### RETURNING (1.0x — expected to play)
| Player | Team | PPG | Notes |
|--------|------|-----|-------|
| Darius Acuff Jr. | Arkansas | 22.7 | Ankle — scored 37 in SEC tourney |
| Darryn Peterson | Kansas | 19.8 | Hamstring — healthy since Feb 9 |
| Christian Anderson | Texas Tech | 18.9 | Groin — available |
| Tyler Bilodeau | UCLA | 17.6 | Knee strain — expected Friday |
| Nolan Winter | Wisconsin | 13.3 | Ankle — coach says definitely ready |
| Donovan Dent | UCLA | 13.5 | Calf strain — expected Friday |
| B.J. Edwards | SMU | 12.7 | Ankle — confirmed available |
| Lamont Butler | Kentucky | 11.5 | Shoulder — cleared for NCAAs |
| Karter Knox | Arkansas | 8.1 | Meniscus surgery — returned for SEC tourney |
| Jalen Warley | Gonzaga | 6.8 | Quad contusion — says ~90% |
