"""
Main pipeline: March Madness Player Scoring Projections

Usage:
    python src/main.py

Requires data/kenpom_tournament.csv and data/bracket.json to exist.
Run src/parse_kenpom.py first if kenpom_tournament.csv is missing.

Pipeline steps:
1. Load KenPom team ratings (AdjO, AdjD, AdjT)
2. Load bracket (64 teams, 4 regions)
3. Load/scrape per-player season stats from ESPN (with ESPN IDs)
4. Load injury data (manual overrides + ESPN scrape)
5. Adjust KenPom for injuries + simulate bracket (expected games + round context)
6. Scrape recent form (last 5 game PPG from ESPN game logs)
7. Project points: per-round PPG × pace × defense × injury, blended with recent form

Outputs:
- output/projections.csv  (ranked player projections)
- docs/players.json       (deployed to web draft board)

To reuse next year: see README.md "How to Reuse This for Next Year"
"""
import os
import sys
import json
from datetime import datetime, timezone
import pandas as pd

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from simulate_bracket import calculate_expected_games, calculate_round_context, adjust_kenpom_for_injuries
from scrape_players_espn import scrape_all_tournament_teams, scrape_recent_form, ESPN_TEAM_IDS
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
    print("\n[1/7] Loading KenPom data...")
    kenpom_path = os.path.join(DATA_DIR, 'kenpom_tournament.csv')
    if not os.path.exists(kenpom_path):
        print("ERROR: kenpom_tournament.csv not found. Run parse_kenpom.py first.")
        return
    kenpom_df = pd.read_csv(kenpom_path)
    # Rename columns to match what simulate_bracket expects
    kenpom_df = kenpom_df.rename(columns={'ORtg': 'AdjO', 'DRtg': 'AdjD'})
    print(f"  Loaded {len(kenpom_df)} tournament teams from KenPom")

    # Step 2: Load bracket
    print("\n[2/7] Loading bracket...")
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

    # Step 3: Load player stats
    print("\n[3/7] Loading player stats...")
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
            player_stats = player_stats.drop_duplicates(subset=['player', 'team'], keep='last')
            player_stats.to_csv(stats_path, index=False)
        print(f"  Loaded {len(player_stats)} player records")
    else:
        print("  No cached stats found. Scraping all teams (this takes a few minutes)...")
        teams = sorted(bracket_teams)
        player_stats = scrape_all_tournament_teams(teams, use_cache=True, delay=3.0)

    if player_stats.empty:
        print("ERROR: No player stats available.")
        return

    # Filter to bracket teams + First Four opponents not yet resolved.
    # Both teams in an undecided First Four matchup need to be draftable.
    # Matchups are configured in data/first_four.json — update before draft day.
    first_four_path = os.path.join(DATA_DIR, 'first_four.json')
    if os.path.exists(first_four_path):
        with open(first_four_path) as f:
            FIRST_FOUR_PAIRS = [tuple(p) for p in json.load(f).get('matchups', [])]
    else:
        FIRST_FOUR_PAIRS = []
    first_four_extras = set()
    for team_a, team_b in FIRST_FOUR_PAIRS:
        if team_a in bracket_teams and team_b not in bracket_teams:
            first_four_extras.add(team_b)
        elif team_b in bracket_teams and team_a not in bracket_teams:
            first_four_extras.add(team_a)
    all_eligible = bracket_teams | first_four_extras
    if first_four_extras:
        print(f"  Including First Four opponents not yet resolved: {first_four_extras}")
    player_stats = player_stats[player_stats['team'].isin(all_eligible)]

    # Step 4: Load injuries
    print("\n[4/7] Loading injury data...")
    injuries = get_combined_injuries(tournament_teams=sorted(all_eligible))

    # Step 5: Adjust KenPom for injuries and simulate bracket
    print("\n[5/7] Adjusting KenPom for injured players and simulating bracket...")
    kenpom_adjusted = adjust_kenpom_for_injuries(kenpom_df, injuries, player_stats)
    expected_games = calculate_expected_games(kenpom_adjusted, bracket)
    round_context = calculate_round_context(kenpom_adjusted, bracket)

    # Give First Four opponents the same expected games / context as their bracket counterpart
    for team_a, team_b in FIRST_FOUR_PAIRS:
        if team_a in expected_games and team_b not in expected_games:
            expected_games[team_b] = expected_games[team_a]
            if team_a in round_context:
                round_context[team_b] = round_context[team_a]
        elif team_b in expected_games and team_a not in expected_games:
            expected_games[team_a] = expected_games[team_b]
            if team_b in round_context:
                round_context[team_a] = round_context[team_b]

    # Print expected games summary
    eg_df = pd.DataFrame([
        {'team': team, 'expected_games': round(eg, 2)}
        for team, eg in sorted(expected_games.items(), key=lambda x: -x[1])
    ])
    print(f"\n  Top 15 teams by expected games:")
    print(eg_df.head(15).to_string(index=False))

    # Step 6: Scrape recent form (last 5 games) for top players
    print("\n[6/7] Loading recent form data...")
    recent_form = scrape_recent_form(player_stats, min_ppg=12.0, last_n=5, delay=2.0)
    if recent_form:
        # Show biggest movers
        movers = []
        for (player, team), recent_ppg in recent_form.items():
            match = player_stats[(player_stats['player'] == player) & (player_stats['team'] == team)]
            if not match.empty:
                season_ppg = match.iloc[0]['ppg']
                diff = recent_ppg - season_ppg
                if abs(diff) >= 2.0:
                    movers.append((player, team, season_ppg, recent_ppg, diff))
        if movers:
            movers.sort(key=lambda x: -x[4])
            print(f"\n  Biggest recent form changes (last 5 vs season):")
            for name, team, szn, rec, diff in movers[:10]:
                print(f"    {name} ({team}): {szn:.1f} -> {rec:.1f} ({diff:+.1f})")
            if len(movers) > 10:
                cold = sorted(movers, key=lambda x: x[4])[:5]
                print(f"  Cooling off:")
                for name, team, szn, rec, diff in cold:
                    print(f"    {name} ({team}): {szn:.1f} -> {rec:.1f} ({diff:+.1f})")

    # Project points
    print("\n" + "=" * 60)
    print("  GENERATING PROJECTIONS")
    print("=" * 60)

    projections = project_player_points(
        player_stats_df=player_stats,
        expected_games=expected_games,
        round_context=round_context,
        injuries_df=injuries,
        recent_form=recent_form,
        min_mpg=10.0
    )

    # Save and display
    output_df = save_projections(projections, kenpom_df=kenpom_df, bracket=bracket)
    print_draft_board(projections, top_n=50)

    # Deploy to docs/ for the web draft board
    docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
    if os.path.isdir(docs_dir):
        docs_path = os.path.join(docs_dir, 'players.json')
        output_df_rounded = output_df.copy()
        output_df_rounded['expected_games'] = output_df_rounded['expected_games'].round(2)

        # Add recent form data for frontend tooltips
        if recent_form:
            # Get original season PPG (before blending)
            season_ppg_map = dict(zip(
                zip(player_stats['player'], player_stats['team']),
                player_stats['ppg'] if 'ppg' in player_stats.columns else []
            ))
            def add_recent(row):
                key = (row['player'], row['team'])
                if key in recent_form:
                    row['recent_ppg'] = recent_form[key]
                    row['season_ppg'] = season_ppg_map.get(key, row['ppg'])
                return row
            output_df_rounded = output_df_rounded.apply(add_recent, axis=1)

        # Add ESPN team IDs for logo URLs
        for _, row in output_df_rounded.iterrows():
            pass  # just need the column
        output_df_rounded['espn_team_id'] = output_df_rounded['team'].map(ESPN_TEAM_IDS)

        # Convert NaN to None for valid JSON (pandas NaN breaks browser JSON.parse)
        import math
        records = output_df_rounded.to_dict('records')
        for rec in records:
            for k, v in rec.items():
                if isinstance(v, float) and math.isnan(v):
                    rec[k] = None
                elif isinstance(v, (int, float)) and k == 'espn_team_id':
                    rec[k] = int(v) if v and not (isinstance(v, float) and math.isnan(v)) else None
        payload = {
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'players': records,
        }
        with open(docs_path, 'w') as f:
            json.dump(payload, f)
        print(f"\nDeployed {len(records)} players to {docs_path}")


if __name__ == '__main__':
    main()
