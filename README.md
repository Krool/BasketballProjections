# March Madness 2026 - Player Scoring Projections

Fantasy draft board for projecting which players will score the most total points in the 2026 NCAA tournament. Built for a 20-person league where each team drafts 14 players (280 total picks).

## How It Works

```
projected_points = PPG * expected_games * injury_multiplier
```

- **PPG**: Season per-game scoring average (scraped from ESPN)
- **Expected games**: Analytically simulated from KenPom adjusted efficiency ratings (AdjO/AdjD) and the actual bracket matchups
- **Injury multiplier**: OUT=0, RETURNING=1.0, DAY-TO-DAY=0.7

The bracket simulation uses probability propagation (not Monte Carlo) -- each team's win probability per round is computed from the KenPom margin formula, weighted by all possible opponents reaching that round.

## Quick Start

```bash
pip install pandas requests beautifulsoup4 numpy

# Run the full pipeline
python src/main.py
```

Output lands in `output/projections.csv`.

## Project Structure

```
data/
  kenpom_raw.txt           # Raw KenPom ratings (paste from kenpom.com)
  kenpom.csv               # Parsed: all 365 D1 teams
  kenpom_tournament.csv    # Parsed: 68 tournament teams with seeds
  bracket.json             # 64-team bracket with region assignments
  injury_overrides.csv     # Manual injury statuses (primary source)
  injuries_combined.csv    # Generated: merged ESPN + manual injuries
  all_player_stats.csv     # Combined player stats from ESPN
  player_stats/            # Per-team JSON cache from ESPN scraping

src/
  main.py                  # Full pipeline orchestrator
  parse_kenpom.py          # Parse raw KenPom data into CSVs
  simulate_bracket.py      # Analytical bracket simulation (expected games)
  scrape_players_espn.py   # Scrape player per-game stats from ESPN
  scrape_injuries.py       # Load injuries (manual overrides + ESPN)
  project_points.py        # Combine data into final projections

output/
  projections.csv          # Final ranked player projections
```

## Updating Data

**New KenPom ratings**: Paste updated table into `data/kenpom_raw.txt`, then run `python src/parse_kenpom.py`.

**Bracket changes**: Edit `data/bracket.json`. Team names must match KenPom exactly.

**Injuries**: Edit `data/injury_overrides.csv`. Name matching is fuzzy on suffixes (Jr., II, III) so "Patrick Ngongba II" matches "Patrick Ngongba".

**Re-scrape player stats**: Delete `data/player_stats/` cache and `data/all_player_stats.csv`, then re-run `python src/main.py`.

## Key Design Decisions

- **Analytical simulation over Monte Carlo**: Deterministic, fast, no random noise. Win probability is computed as `1 / (1 + 10^(-margin/11))` where margin is the KenPom NetRtg difference.
- **ESPN over sports-reference**: Sports-reference rate-limits aggressively after ~30 requests. ESPN handles 64 teams without issues.
- **Fuzzy injury matching**: Player names vary across sources (ESPN drops "Jr.", news adds "II"). Names are normalized by stripping suffixes before matching.
- **First Four skipped**: Bracket starts at Round of 64. Play-in winners were selected by higher KenPom rating.
