"""
Project total tournament scoring for each player.

Core formula: projected_points = PPG * expected_games * injury_multiplier

Injury multipliers: OUT=0.0, RETURNING=0.8, DAY-TO-DAY=0.7, HEALTHY=1.0

Player names are fuzzy-matched against injury data by stripping suffixes
(Jr., Sr., II, III, etc.) so that "Patrick Ngongba II" in the injury file
correctly matches "Patrick Ngongba" from ESPN.
"""
import os
import re
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')

# Suffixes that vary between data sources (ESPN vs news articles vs manual entry)
_SUFFIX_RE = re.compile(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$', re.IGNORECASE)


def _normalize_name(name):
    """
    Normalize a player name for matching across data sources.
    Strips suffixes like Jr., Sr., II, III, etc. and lowercases.
    """
    name = str(name).strip().lower()
    name = _SUFFIX_RE.sub('', name)
    return name.strip()


def _build_injury_lookup(injuries_df):
    """
    Build an injury lookup dict that can match on both exact and
    suffix-stripped names. Exact matches take priority.
    """
    exact_lookup = {}   # (player_lower, team_lower) -> status
    fuzzy_lookup = {}   # (normalized_name, team_lower) -> status

    for _, row in injuries_df.iterrows():
        player = str(row['player']).strip()
        team = str(row['team']).strip().lower()
        status = str(row['status']).strip().upper()

        exact_lookup[(player.lower(), team)] = status
        fuzzy_lookup[(_normalize_name(player), team)] = status

    return exact_lookup, fuzzy_lookup


def _get_injury_status(player_name, team_name, exact_lookup, fuzzy_lookup):
    """Look up injury status, trying exact match first, then normalized."""
    team = team_name.lower()

    # Try exact match
    status = exact_lookup.get((player_name.lower(), team))
    if status:
        return status

    # Try normalized (suffix-stripped) match
    status = fuzzy_lookup.get((_normalize_name(player_name), team))
    if status:
        return status

    return 'HEALTHY'


def project_player_points(player_stats_df, expected_games, injuries_df=None, min_mpg=10.0):
    """
    Project total tournament points for each player.

    Args:
        player_stats_df: DataFrame with columns [player, team, ppg, mpg, games_played]
        expected_games: dict of {team_name: expected_games_float}
        injuries_df: DataFrame with columns [player, team, status] (optional)
        min_mpg: minimum minutes per game to include player

    Returns:
        DataFrame sorted by projected_points descending
    """
    # Filter to meaningful players
    df = player_stats_df[player_stats_df['mpg'] >= min_mpg].copy()

    # Add expected games for each player's team
    df['expected_games'] = df['team'].map(expected_games)

    # Drop players whose teams aren't in the bracket
    df = df.dropna(subset=['expected_games'])

    # Apply injury adjustments
    if injuries_df is not None and not injuries_df.empty:
        exact_lookup, fuzzy_lookup = _build_injury_lookup(injuries_df)

        def get_injury_multiplier(row):
            status = _get_injury_status(row['player'], row['team'], exact_lookup, fuzzy_lookup)
            if status == 'OUT':
                return 0.0
            elif status == 'RETURNING':
                return 0.8  # Expected to play but may have limited minutes
            elif status == 'DAY-TO-DAY':
                return 0.7  # Discount for uncertainty
            else:
                return 1.0  # Healthy

        df['injury_multiplier'] = df.apply(get_injury_multiplier, axis=1)
        df['injury_status'] = df.apply(
            lambda row: _get_injury_status(row['player'], row['team'], exact_lookup, fuzzy_lookup),
            axis=1
        )
    else:
        df['injury_multiplier'] = 1.0
        df['injury_status'] = 'HEALTHY'

    # Calculate projected points
    df['projected_points'] = (df['ppg'] * df['expected_games'] * df['injury_multiplier']).round(1)

    # Sort by projected points
    df = df.sort_values('projected_points', ascending=False).reset_index(drop=True)
    df.index = df.index + 1  # 1-based ranking
    df.index.name = 'rank'

    return df


def save_projections(df, kenpom_df=None, bracket=None):
    """Save projections to CSV and print summary."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Add seed info if kenpom data is available
    if kenpom_df is not None:
        seed_map = dict(zip(kenpom_df['Team'], kenpom_df['Seed']))
        df['seed'] = df['team'].map(seed_map)

    # Add region info if bracket is available
    if bracket is not None:
        region_map = {}
        for region, seeds in bracket.get('regions', {}).items():
            for seed, team in seeds.items():
                if team:
                    region_map[team] = region
        df['region'] = df['team'].map(region_map)

    # Select output columns — include rank from index
    df['rank'] = df.index
    output_cols = ['rank', 'player', 'team']
    if 'seed' in df.columns:
        output_cols.append('seed')
    if 'region' in df.columns:
        output_cols.append('region')
    output_cols.extend(['ppg', 'expected_games', 'injury_status', 'projected_points'])

    output_df = df[output_cols].copy()

    # Save full list
    output_path = os.path.join(OUTPUT_DIR, 'projections.csv')
    output_df.to_csv(output_path, index=False)
    print(f"Saved {len(output_df)} player projections to {output_path}")

    return output_df


def print_draft_board(df, top_n=50):
    """Print a formatted draft board."""
    print(f"\n{'='*80}")
    print(f"  MARCH MADNESS 2026 - PROJECTED SCORING LEADERS")
    print(f"  Fantasy Draft Board (20 teams x 14 players = 280 picks)")
    print(f"{'='*80}\n")

    display_cols = ['player', 'team']
    if 'seed' in df.columns:
        display_cols.append('seed')
    display_cols.extend(['ppg', 'expected_games', 'injury_status', 'projected_points'])

    top = df.head(top_n)[display_cols]

    # Format expected_games to 2 decimal places
    top = top.copy()
    top['expected_games'] = top['expected_games'].round(2)

    print(top.to_string())

    print(f"\n{'='*80}")
    print(f"  Total players projected: {len(df)}")
    print(f"  Players needed for draft: 280")

    out_players = df[df['injury_status'] == 'OUT']
    if len(out_players) > 0:
        print(f"\n  Players marked OUT ({len(out_players)}):")
        for _, p in out_players.iterrows():
            print(f"    - {p['player']} ({p['team']})")

    print(f"{'='*80}\n")
