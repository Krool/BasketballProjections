"""Field-name constants and validation helpers for archive CSVs.

Centralizes the schema for files under `archive/<year>/actual/` and the
analysis outputs in `archive/<year>/analysis/`. Other scripts should import
field names from here so a rename in one place breaks all dependents loudly
at import time instead of silently producing wrong analysis.

If you change a field name, update the matching FIELDS_* tuple here.
"""
from __future__ import annotations

import csv
from pathlib import Path

# ---------- player_results.csv ----------
# Round-by-round actuals for every drafted player. Round columns are empty
# string for "did not play" (DNP) and an integer for played (0 = played but
# scored 0). games_played is the count of non-empty round columns.
COL_PLAYER = "player"
COL_TEAM = "team"
COL_ENTRY = "entry"
COL_ESPN_ID = "espn_id"
COL_R64 = "r64"
COL_R32 = "r32"
COL_S16 = "s16"
COL_E8 = "e8"
COL_F4 = "f4"
COL_CHAMP = "championship"
COL_GAMES_PLAYED = "games_played"
COL_TOTAL_POINTS = "total_points"
COL_ALIVE = "alive"
COL_IN_TOURNAMENT_INJURY = "in_tournament_injury"

ROUND_COLS = (COL_R64, COL_R32, COL_S16, COL_E8, COL_F4, COL_CHAMP)

FIELDS_PLAYER_RESULTS = (
    COL_PLAYER, COL_TEAM, COL_ENTRY, COL_ESPN_ID,
    *ROUND_COLS,
    COL_GAMES_PLAYED, COL_TOTAL_POINTS, COL_ALIVE, COL_IN_TOURNAMENT_INJURY,
)

# ---------- draft_picks.csv ----------
COL_PICK = "pick"
COL_ROUND = "round"

FIELDS_DRAFT_PICKS = (
    COL_ROUND, COL_PICK, COL_ENTRY, COL_PLAYER, COL_TEAM, COL_ESPN_ID,
)

# ---------- entry_totals.csv ----------
COL_TOTAL = "total"
COL_PLAYERS_LEFT = "players_left"
COL_ADRRP = "adrrp"

FIELDS_ENTRY_TOTALS = (
    COL_ENTRY, *ROUND_COLS, COL_TOTAL, COL_PLAYERS_LEFT, COL_ADRRP,
)

# ---------- bracket_outcome.json keys ----------
BO_YEAR = "year"
BO_CHAMPION = "champion"
BO_FINALISTS = "finalists"
BO_FINAL_FOUR = "final_four"
BO_ELITE_EIGHT = "elite_eight"
BO_SWEET_SIXTEEN = "sweet_sixteen"
BO_ROUND_OF_32 = "round_of_32"
BO_GAMES = "games"

# Per-game keys inside bracket_outcome.games[]
GAME_ROUND = "round"
GAME_REGION = "region"
GAME_WINNER = "winner"
GAME_WINNER_SEED = "winner_seed"
GAME_WINNER_SCORE = "winner_score"
GAME_LOSER = "loser"
GAME_LOSER_SEED = "loser_seed"
GAME_LOSER_SCORE = "loser_score"

# Round identifier values used in games[]
ROUND_R64 = "r64"
ROUND_R32 = "r32"
ROUND_S16 = "s16"
ROUND_E8 = "e8"
ROUND_F4 = "f4"
ROUND_CHAMPIONSHIP = "championship"

EXPECTED_GAMES_PER_ROUND = {
    ROUND_R64: 32,
    ROUND_R32: 16,
    ROUND_S16: 8,
    ROUND_E8: 4,
    ROUND_F4: 2,
    ROUND_CHAMPIONSHIP: 1,
}
EXPECTED_TOTAL_GAMES = sum(EXPECTED_GAMES_PER_ROUND.values())  # 63


def validate_csv_headers(path: Path, expected_fields: tuple[str, ...]) -> list[str]:
    """Return a list of missing required field names. Empty = all present.

    Extra fields are allowed (forward-compat). Missing fields are reported.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return list(expected_fields)
    return [f for f in expected_fields if f not in header]


def validate_bracket_games(games: list[dict]) -> list[str]:
    """Return a list of structural problems with a games[] array. Empty = OK."""
    problems = []
    if len(games) != EXPECTED_TOTAL_GAMES:
        problems.append(
            f"games[] has {len(games)} entries, expected {EXPECTED_TOTAL_GAMES}"
        )
    counts = {}
    for g in games:
        counts[g.get(GAME_ROUND)] = counts.get(g.get(GAME_ROUND), 0) + 1
    for round_id, expected in EXPECTED_GAMES_PER_ROUND.items():
        actual = counts.get(round_id, 0)
        if actual != expected:
            problems.append(f"round {round_id}: {actual} games, expected {expected}")
    # Check that winners of round N are exactly the participants of round N+1
    # (advancement consistency)
    progression = [
        (ROUND_R64, ROUND_R32),
        (ROUND_R32, ROUND_S16),
        (ROUND_S16, ROUND_E8),
        (ROUND_E8, ROUND_F4),
        (ROUND_F4, ROUND_CHAMPIONSHIP),
    ]
    for src, dst in progression:
        winners = {g[GAME_WINNER] for g in games if g.get(GAME_ROUND) == src}
        next_teams = set()
        for g in games:
            if g.get(GAME_ROUND) == dst:
                next_teams.add(g[GAME_WINNER])
                next_teams.add(g[GAME_LOSER])
        missing = next_teams - winners
        if missing:
            problems.append(
                f"round {dst} includes teams that didn't win {src}: {sorted(missing)}"
            )
    return problems
