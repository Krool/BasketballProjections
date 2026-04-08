"""
Project total tournament scoring for each player.

Scoring model per round:
    round_pts = PPG * pace_factor * defense_factor * injury_mult
    projected_points = sum(p_play_round * round_pts for each round)

Adjustments:
    - Recent form: PPG blended 60% season + 40% last 5 games
    - Pace: normalize PPG to expected matchup tempo vs team's season tempo
    - Defense: scale scoring by opponent DRtg vs D1 average (100.0)
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





def _normalize_name(name):
    """
    Normalize a player name for matching across data sources.
    Strips suffixes like Jr., Sr., II, III, etc., removes apostrophes
    and special characters, and lowercases.
    """
    name = str(name).strip().lower()
    name = _SUFFIX_RE.sub('', name)
    # Remove apostrophes and special chars for matching (Dell'Orso -> dellorso)
    name = name.replace("'", "").replace("'", "").replace("-", "")
    return name.strip()


def _build_injury_lookup(injuries_df):
    """
    Build injury lookup dicts for status and games_missed.
    Matches on both exact and suffix-stripped names.
    """
    exact_lookup = {}   # (player_lower, team_lower) -> (status, games_missed)
    fuzzy_lookup = {}   # (normalized_name, team_lower) -> (status, games_missed)

    for _, row in injuries_df.iterrows():
        player = str(row['player']).strip()
        team = str(row['team']).strip().lower()
        status = str(row['status']).strip().upper()
        games_missed = int(row['games_missed']) if 'games_missed' in row.index and pd.notna(row.get('games_missed')) else (6 if status == 'OUT' else 0)

        fitness = float(row['fitness']) if 'fitness' in row.index and pd.notna(row.get('fitness')) else (0.0 if status == 'OUT' else 1.0)

        exact_lookup[(player.lower(), team)] = (status, games_missed, fitness)
        fuzzy_lookup[(_normalize_name(player), team)] = (status, games_missed, fitness)

    return exact_lookup, fuzzy_lookup


def _get_injury_info(player_name, team_name, exact_lookup, fuzzy_lookup):
    """Look up injury status and games_missed, trying exact match first."""
    team = team_name.lower()

    result = exact_lookup.get((player_name.lower(), team))
    if result:
        return result

    result = fuzzy_lookup.get((_normalize_name(player_name), team))
    if result:
        return result

    return ('HEALTHY', 0, 1.0)



# Recent form blending: weight recent games vs season average.
# 60% season + 40% recent captures "hot hand" without overreacting to noise.
RECENT_FORM_WEIGHT = 0.40


def project_player_points(player_stats_df, expected_games, round_context=None,
                          injuries_df=None, recent_form=None, min_mpg=10.0):
    """
    Project total tournament points for each player.

    Uses per-round matchup context (opponent defense, pace, blowout potential)
    when available, otherwise falls back to flat PPG * expected_games.

    Args:
        player_stats_df: DataFrame with columns [player, team, ppg, mpg, games_played]
        expected_games: dict of {team_name: expected_games_float}
        round_context: dict from calculate_round_context() (optional)
        injuries_df: DataFrame with columns [player, team, status] (optional)
        recent_form: dict of {(player, team): recent_ppg} (optional)
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

    # Blend recent form with season PPG
    if recent_form:
        def blend_ppg(row):
            key = (row['player'], row['team'])
            if key in recent_form:
                recent = recent_form[key]
                season = row['ppg']
                return round((1 - RECENT_FORM_WEIGHT) * season + RECENT_FORM_WEIGHT * recent, 1)
            return row['ppg']

        df['ppg'] = df.apply(blend_ppg, axis=1)

    # Apply injury adjustments
    if injuries_df is not None and not injuries_df.empty:
        exact_lookup, fuzzy_lookup = _build_injury_lookup(injuries_df)

        def get_injury_info(row):
            return _get_injury_info(row['player'], row['team'], exact_lookup, fuzzy_lookup)

        df[['injury_status', 'games_missed', 'fitness_mult']] = df.apply(
            lambda row: pd.Series(get_injury_info(row)), axis=1
        )
    else:
        df['injury_status'] = 'HEALTHY'
        df['games_missed'] = 0
        df['fitness_mult'] = 1.0

    # Calculate projected points
    if round_context:
        # Per-round matchup-adjusted scoring, skipping missed rounds
        def compute_adjusted(row):
            tc = round_context.get(row['team'])
            if not tc:
                return row['ppg'] * max(0, row['expected_games'] - row['games_missed']) * row['fitness_mult']

            ppg = row['ppg']
            team_adjt = tc['adj_t']
            fitness = row['fitness_mult']
            skip = int(row['games_missed'])
            total = 0.0

            for i, rd in enumerate(tc['rounds']):
                # Skip first N rounds the player will miss
                if i < skip:
                    continue

                # Pace: tournament game pace = avg of both teams' tempo
                matchup_pace = (team_adjt + rd['opp_adjt']) / 2
                pace_factor = matchup_pace / team_adjt

                # Defense: opponent allows more/fewer points than D1 average
                defense_factor = rd['opp_drtg'] / D1_AVG_DRTG

                # Expected points this round
                round_pts = ppg * pace_factor * defense_factor * fitness
                total += rd['p_play'] * round_pts

            return round(total, 1)

        df['projected_points'] = df.apply(compute_adjusted, axis=1)
    else:
        # Fallback: flat PPG * expected_games
        df['projected_points'] = (
            df['ppg']
            * (df['expected_games'] - df['games_missed']).clip(lower=0)
            * df['fitness_mult']
        ).round(1)

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
