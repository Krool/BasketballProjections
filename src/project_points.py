"""
Project total tournament scoring for each player.

Scoring model per round:
    round_pts = PPG * pace_factor * defense_factor * blowout_factor * injury_mult
    projected_points = sum(p_play_round * round_pts for each round)

Adjustments:
    - Pace: normalize PPG to expected matchup tempo vs team's season tempo
    - Defense: scale scoring by opponent DRtg vs D1 average (100.0)
    - Blowout: reduce minutes (and scoring) in expected blowouts
    - Injury: OUT=0.0, DAY-TO-DAY=0.7, PROBABLE=0.9, RETURNING=0.8, HEALTHY=1.0

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

# D-I average defensive efficiency (KenPom centers on ~100)
D1_AVG_DRTG = 100.0

# Injury multipliers
INJURY_MULTIPLIERS = {
    'OUT': 0.0,
    'DAY-TO-DAY': 0.7,      # Truly uncertain — missed recent games, status unknown
    'PROBABLE': 0.9,         # Expected to play, minor lingering issue
    'RETURNING': 0.8,        # Back from injury but may have limited minutes / rust
    'HEALTHY': 1.0,
}


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


def _blowout_factor(expected_margin):
    """
    Reduce scoring in expected blowouts where starters sit early.

    Uses absolute margin — both the team winning by 30 AND the team losing
    by 30 see reduced starter minutes in garbage time.

    In a close game (|margin| <= 5), full minutes. As margin grows, starters
    sit earlier: ~30 min at +/-15, ~26 min at +/-25, ~23 min at +/-35.
    """
    abs_margin = abs(expected_margin)
    if abs_margin <= 5:
        return 1.0
    return max(0.70, 1.0 - (abs_margin - 5) * 0.008)


def project_player_points(player_stats_df, expected_games, round_context=None,
                          injuries_df=None, min_mpg=10.0):
    """
    Project total tournament points for each player.

    Uses per-round matchup context (opponent defense, pace, blowout potential)
    when available, otherwise falls back to flat PPG * expected_games.

    Args:
        player_stats_df: DataFrame with columns [player, team, ppg, mpg, games_played]
        expected_games: dict of {team_name: expected_games_float}
        round_context: dict from calculate_round_context() (optional)
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
            return INJURY_MULTIPLIERS.get(status, 1.0)

        df['injury_multiplier'] = df.apply(get_injury_multiplier, axis=1)
        df['injury_status'] = df.apply(
            lambda row: _get_injury_status(row['player'], row['team'], exact_lookup, fuzzy_lookup),
            axis=1
        )
    else:
        df['injury_multiplier'] = 1.0
        df['injury_status'] = 'HEALTHY'

    # Calculate projected points
    if round_context:
        # Per-round matchup-adjusted scoring
        def compute_adjusted(row):
            tc = round_context.get(row['team'])
            if not tc:
                return row['ppg'] * row['expected_games'] * row['injury_multiplier']

            ppg = row['ppg']
            team_adjt = tc['adj_t']
            injury_mult = row['injury_multiplier']
            total = 0.0

            for rd in tc['rounds']:
                # Pace: tournament game pace = avg of both teams' tempo
                matchup_pace = (team_adjt + rd['opp_adjt']) / 2
                pace_factor = matchup_pace / team_adjt

                # Defense: opponent allows more/fewer points than D1 average
                defense_factor = rd['opp_drtg'] / D1_AVG_DRTG

                # Blowout: starters sit in blowouts
                blowout = _blowout_factor(rd['margin'])

                # Expected points this round
                round_pts = ppg * pace_factor * defense_factor * blowout * injury_mult
                total += rd['p_play'] * round_pts

            return round(total, 1)

        df['projected_points'] = df.apply(compute_adjusted, axis=1)
    else:
        # Fallback: flat PPG * expected_games
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
