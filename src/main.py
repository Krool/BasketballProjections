"""
Main pipeline: March Madness 2026 Player Scoring Projections

Usage:
    python src/main.py

Requires data/kenpom_tournament.csv and data/bracket.json to exist.
Run src/parse_kenpom.py first if kenpom_tournament.csv is missing.

Pipeline steps:
1. Load KenPom team ratings (AdjO, AdjD)
2. Load bracket (64 teams, 4 regions)
3. Simulate bracket analytically to get expected games per team
4. Load/scrape per-player season stats (PPG) from ESPN
5. Load injury data (manual overrides + ESPN scrape)
6. Compute projected points = PPG * expected_games * injury_multiplier
"""
import os
import sys
import json
import pandas as pd

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from simulate_bracket import calculate_expected_games
from scrape_players_espn import scrape_all_tournament_teams
from scrape_injuries import get_combined_injuries
from project_points import project_player_points, save_projections, print_draft_board

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def get_bracket_teams(bracket):
    """Extract the 64 team names from the bracket."""
    teams = set()
    for region, seeds in bracket['regions'].items():
        for seed, team in seeds.items():
            if team:
                teams.add(team)
    return teams


def main():
    print("=" * 60)
    print("  MARCH MADNESS 2026 SCORING PROJECTIONS PIPELINE")
    print("=" * 60)

    # Step 1: Load KenPom data
    print("\n[1/5] Loading KenPom data...")
    kenpom_path = os.path.join(DATA_DIR, 'kenpom_tournament.csv')
    if not os.path.exists(kenpom_path):
        print("ERROR: kenpom_tournament.csv not found. Run parse_kenpom.py first.")
        return
    kenpom_df = pd.read_csv(kenpom_path)
    # Rename columns to match what simulate_bracket expects
    kenpom_df = kenpom_df.rename(columns={'ORtg': 'AdjO', 'DRtg': 'AdjD'})
    print(f"  Loaded {len(kenpom_df)} tournament teams from KenPom")

    # Step 2: Load bracket
    print("\n[2/5] Loading bracket...")
    bracket_path = os.path.join(DATA_DIR, 'bracket.json')
    if not os.path.exists(bracket_path):
        print("ERROR: bracket.json not found. Please create it first.")
        return

    try:
        with open(bracket_path) as f:
            bracket = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: bracket.json is malformed: {e}")
        return

    bracket_teams = get_bracket_teams(bracket)
    print(f"  Loaded bracket with {len(bracket.get('regions', {}))} regions, {len(bracket_teams)} teams")

    # Step 3: Calculate expected games
    print("\n[3/5] Simulating bracket for expected games...")
    expected_games = calculate_expected_games(kenpom_df, bracket)

    # Print expected games summary
    eg_df = pd.DataFrame([
        {'team': team, 'expected_games': round(eg, 2)}
        for team, eg in sorted(expected_games.items(), key=lambda x: -x[1])
    ])
    print(f"\n  Top 15 teams by expected games:")
    print(eg_df.head(15).to_string(index=False))

    # Step 4: Load player stats
    print("\n[4/5] Loading player stats...")
    stats_path = os.path.join(DATA_DIR, 'all_player_stats.csv')
    if os.path.exists(stats_path):
        player_stats = pd.read_csv(stats_path)
        # Check if we have stats for all bracket teams
        cached_teams = set(player_stats['team'].unique())
        missing = bracket_teams - cached_teams
        if missing:
            print(f"  Missing stats for {len(missing)} teams, scraping: {missing}")
            new_stats = scrape_all_tournament_teams(sorted(missing), use_cache=True, delay=3.0)
            player_stats = pd.concat([player_stats, new_stats], ignore_index=True)
            player_stats.to_csv(stats_path, index=False)
        print(f"  Loaded {len(player_stats)} player records")
    else:
        print("  No cached stats found. Scraping all teams (this takes a few minutes)...")
        teams = sorted(bracket_teams)
        player_stats = scrape_all_tournament_teams(teams, use_cache=True, delay=3.0)

    if player_stats.empty:
        print("ERROR: No player stats available.")
        return

    # Filter to bracket teams only
    player_stats = player_stats[player_stats['team'].isin(bracket_teams)]

    # Step 5: Load injuries
    print("\n[5/5] Loading injury data...")
    injuries = get_combined_injuries(tournament_teams=sorted(bracket_teams))

    # Project points
    print("\n" + "=" * 60)
    print("  GENERATING PROJECTIONS")
    print("=" * 60)

    projections = project_player_points(
        player_stats_df=player_stats,
        expected_games=expected_games,
        injuries_df=injuries,
        min_mpg=10.0
    )

    # Save and display
    output_df = save_projections(projections, kenpom_df=kenpom_df)
    print_draft_board(projections, top_n=50)


if __name__ == '__main__':
    main()
