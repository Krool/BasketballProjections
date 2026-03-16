"""
Analytical NCAA Tournament bracket simulation.

Computes each team's probability of reaching and winning each round,
then derives expected games played (useful for fantasy/projection scoring).

No Monte Carlo -- pure probability propagation through the bracket tree.
"""

import json
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# Win-probability model (KenPom-style log-linear)
# ---------------------------------------------------------------------------

def win_probability(adj_o_a, adj_d_a, adj_o_b, adj_d_b):
    """
    Probability that team A beats team B on a neutral court.

    Parameters
    ----------
    adj_o_a, adj_d_a : float
        Team A adjusted offensive / defensive efficiency.
    adj_o_b, adj_d_b : float
        Team B adjusted offensive / defensive efficiency.

    Returns
    -------
    float  in (0, 1)
    """
    # Positive margin means A is better
    # margin = NetRtg_A - NetRtg_B = (AdjO_A - AdjD_A) - (AdjO_B - AdjD_B)
    margin = (adj_o_a - adj_d_a) - (adj_o_b - adj_d_b)
    return 1.0 / (1.0 + 10.0 ** (-margin / 11.0))


# ---------------------------------------------------------------------------
# Bracket topology constants
# ---------------------------------------------------------------------------

# Round 1 matchups by seed (order matters -- it defines the bracket tree)
# Each tuple is a "slot" in the region; the bracket tree is a binary tree
# whose leaves (left-to-right) are these slots in order.
ROUND1_SEEDS = [
    (1, 16),
    (8, 9),
    (5, 12),
    (4, 13),
    (6, 11),
    (3, 14),
    (7, 10),
    (2, 15),
]
# Each tuple defines a first-round matchup. The bracket tree has 16 leaf
# slots (one per team). Adjacent pairs play each other, and winners advance
# through 4 rounds: 16 -> 8 -> 4 -> 2 -> 1 (region champion).


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

class Team:
    """Lightweight container for a tournament team."""
    __slots__ = ("name", "seed", "region", "adj_o", "adj_d")

    def __init__(self, name, seed, region, adj_o, adj_d):
        self.name = name
        self.seed = seed
        self.region = region
        self.adj_o = adj_o
        self.adj_d = adj_d

    def __repr__(self):
        return f"Team({self.name}, {self.seed}, {self.region})"


def _wp(a: Team, b: Team) -> float:
    """Win probability for team *a* over team *b*."""
    return win_probability(a.adj_o, a.adj_d, b.adj_o, b.adj_d)


# ---------------------------------------------------------------------------
# Probability propagation inside a single region (Rounds 1-4)
# ---------------------------------------------------------------------------

def _propagate_region(teams_by_seed: dict[int, Team]) -> dict[str, list[float]]:
    """
    Given 16 teams keyed by seed (1-16), compute for each team the
    probability of *winning* each of the 4 intra-region rounds.

    Returns
    -------
    dict  {team_name: [p_win_r1, p_win_r2, p_win_r3, p_win_r4]}
    """
    # Build leaf slots -- each team is its own slot (16 slots total).
    # The bracket tree pairs adjacent slots: slot0 vs slot1 = 1-seed vs 16-seed, etc.
    slots: list[list[tuple[Team, float]]] = []
    for hi_seed, lo_seed in ROUND1_SEEDS:
        slots.append([(teams_by_seed[hi_seed], 1.0)])
        slots.append([(teams_by_seed[lo_seed], 1.0)])

    # round_probs[team_name][round_idx] = P(win that round)
    all_teams = {t.name: t for t in teams_by_seed.values()}
    round_probs: dict[str, list[float]] = {name: [] for name in all_teams}

    # We do 4 rounds: 16→8→4→2→1
    current_slots = slots

    for round_idx in range(4):
        next_slots: list[list[tuple[Team, float]]] = []

        # Pair up adjacent slots
        for i in range(0, len(current_slots), 2):
            slot_a = current_slots[i]
            slot_b = current_slots[i + 1]

            # For each team in slot_a, compute probability of beating
            # every possible opponent in slot_b (weighted by their presence).
            winners: list[tuple[Team, float]] = []

            for team_a, prob_a in slot_a:
                p_win = 0.0
                for team_b, prob_b in slot_b:
                    p_win += prob_b * _wp(team_a, team_b)
                p_advance = prob_a * p_win
                if p_advance > 1e-15:
                    winners.append((team_a, p_advance))
                round_probs[team_a.name].append(prob_a * p_win)

            for team_b, prob_b in slot_b:
                p_win = 0.0
                for team_a, prob_a in slot_a:
                    p_win += prob_a * _wp(team_b, team_a)
                p_advance = prob_b * p_win
                if p_advance > 1e-15:
                    winners.append((team_b, p_advance))
                round_probs[team_b.name].append(prob_b * p_win)

            next_slots.append(winners)

        current_slots = next_slots

    # current_slots is now a single list with one entry (the region champion
    # probability distribution).  That was already recorded in round_probs.

    return round_probs, current_slots[0]


# ---------------------------------------------------------------------------
# Final Four + Championship (Rounds 5-6)
# ---------------------------------------------------------------------------

def _propagate_final_four(
    region_champions: dict[str, list[tuple[Team, float]]],
    ff_matchups: list[list[str]],
) -> dict[str, list[float]]:
    """
    Given region champion distributions and Final Four pairing,
    compute P(win semifinal) and P(win championship) for each team.

    Parameters
    ----------
    region_champions : {region_name: [(Team, prob), ...]}
    ff_matchups : [[regionA, regionB], [regionC, regionD]]

    Returns
    -------
    dict  {team_name: [p_win_semifinal, p_win_final]}
    """
    round_probs: dict[str, list[float]] = {}
    semifinal_winners: list[list[tuple[Team, float]]] = []

    for reg_a_name, reg_b_name in ff_matchups:
        slot_a = region_champions[reg_a_name]
        slot_b = region_champions[reg_b_name]
        winners: list[tuple[Team, float]] = []

        for team_a, prob_a in slot_a:
            p_win = 0.0
            for team_b, prob_b in slot_b:
                p_win += prob_b * _wp(team_a, team_b)
            p_advance = prob_a * p_win
            round_probs.setdefault(team_a.name, []).append(prob_a * p_win)
            if p_advance > 1e-15:
                winners.append((team_a, p_advance))

        for team_b, prob_b in slot_b:
            p_win = 0.0
            for team_a, prob_a in slot_a:
                p_win += prob_a * _wp(team_b, team_a)
            p_advance = prob_b * p_win
            round_probs.setdefault(team_b.name, []).append(prob_b * p_win)
            if p_advance > 1e-15:
                winners.append((team_b, p_advance))

        semifinal_winners.append(winners)

    # Championship
    slot_a = semifinal_winners[0]
    slot_b = semifinal_winners[1]

    for team_a, prob_a in slot_a:
        p_win = 0.0
        for team_b, prob_b in slot_b:
            p_win += prob_b * _wp(team_a, team_b)
        round_probs[team_a.name].append(prob_a * p_win)

    for team_b, prob_b in slot_b:
        p_win = 0.0
        for team_a, prob_a in slot_a:
            p_win += prob_a * _wp(team_b, team_a)
        round_probs[team_b.name].append(prob_b * p_win)

    return round_probs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_bracket(path: str | Path) -> dict:
    """Load bracket.json and return the parsed dict."""
    with open(path, "r") as f:
        return json.load(f)


def build_teams(kenpom_df: pd.DataFrame, bracket: dict) -> dict[str, dict[int, Team]]:
    """
    Match KenPom rows to bracket entries and build Team objects.

    Parameters
    ----------
    kenpom_df : DataFrame
        Must contain columns: Team, AdjO, AdjD.
        Team names must match bracket entries exactly.
    bracket : dict
        Parsed bracket.json.

    Returns
    -------
    dict  {region_name: {seed_int: Team}}
    """
    # Build lookup from team name -> (AdjO, AdjD)
    stats = {}
    for _, row in kenpom_df.iterrows():
        stats[row["Team"]] = (float(row["AdjO"]), float(row["AdjD"]))

    regions: dict[str, dict[int, Team]] = {}
    missing = []

    for region_name, seeds in bracket["regions"].items():
        region_teams: dict[int, Team] = {}
        for seed_str, team_name in seeds.items():
            seed = int(seed_str)
            if not team_name:
                missing.append(f"{region_name} seed {seed}")
                continue
            if team_name not in stats:
                raise KeyError(
                    f"Team '{team_name}' (seed {seed}, {region_name}) "
                    f"not found in KenPom data. Check name spelling."
                )
            adj_o, adj_d = stats[team_name]
            region_teams[seed] = Team(team_name, seed, region_name, adj_o, adj_d)
        regions[region_name] = region_teams

    if missing:
        raise ValueError(
            f"Bracket has {len(missing)} empty slots. "
            f"Fill in bracket.json before simulating. "
            f"First few: {missing[:5]}"
        )

    return regions


def calculate_expected_games(kenpom_df: pd.DataFrame, bracket: dict) -> dict[str, float]:
    """
    Analytical tournament simulation.

    For each of the 64 teams, compute the expected number of games played
    (between 1 and 6).  Every team plays at least 1 game.

    Parameters
    ----------
    kenpom_df : DataFrame
        Columns: Team, AdjO, AdjD (at minimum).
    bracket : dict
        Parsed bracket.json with all 64 team slots filled.

    Returns
    -------
    dict  {team_name: expected_games}
    """
    regions = build_teams(kenpom_df, bracket)
    ff_matchups = bracket.get("final_four_matchups", [["East", "West"], ["South", "Midwest"]])

    # --- Rounds 1-4 (within each region) ---
    region_round_probs: dict[str, list[float]] = {}   # team -> [p_win_r1..r4]
    region_champions: dict[str, list[tuple[Team, float]]] = {}

    for region_name, seed_map in regions.items():
        rp, champs = _propagate_region(seed_map)
        for tname, probs in rp.items():
            region_round_probs[tname] = probs
        region_champions[region_name] = champs

    # --- Rounds 5-6 (Final Four + Championship) ---
    ff_probs = _propagate_final_four(region_champions, ff_matchups)

    # --- Combine into expected games ---
    # EG = 1 + P(win R1) + P(win R2) + P(win S16) + P(win E8) + P(win F4 semi)
    #
    # Each P(win round k) = P(you advance to round k+1) = P(you play round k+1).
    # You always play R1 (= 1 game). Winning the championship does NOT add a game
    # (there's no game after the final), so we exclude P(win CG).

    expected: dict[str, float] = {}
    for tname, r14 in region_round_probs.items():
        # r14 has 4 entries: [p_win_r1, p_win_r2, p_win_r3, p_win_r4]
        eg = 1.0  # always play round 1
        for p in r14:
            eg += p  # each win means you play the next round
        # Add Final Four semifinal only (not championship win)
        # ff_probs[tname] = [p_win_semifinal, p_win_championship]
        if tname in ff_probs:
            eg += ff_probs[tname][0]  # semifinal win = play championship
            # ff_probs[tname][1] is P(win CG) -- excluded, no next game
        expected[tname] = eg

    return expected


def calculate_round_probabilities(kenpom_df: pd.DataFrame, bracket: dict) -> dict[str, dict]:
    """
    Return detailed round-by-round probabilities for every team.

    Returns
    -------
    dict  {team_name: {
        "seed": int,
        "region": str,
        "expected_games": float,
        "round_probs": {
            "R64_win": float,    # P(win Round of 64)
            "R32_win": float,    # P(win Round of 32)
            "S16_win": float,    # P(win Sweet 16)
            "E8_win": float,     # P(win Elite 8)
            "F4_win": float,     # P(win Final Four semifinal)
            "CG_win": float,     # P(win Championship)
        }
    }}
    """
    regions = build_teams(kenpom_df, bracket)
    ff_matchups = bracket.get("final_four_matchups", [["East", "West"], ["South", "Midwest"]])

    region_round_probs: dict[str, list[float]] = {}
    region_champions: dict[str, list[tuple[Team, float]]] = {}
    team_meta: dict[str, tuple[int, str]] = {}  # team -> (seed, region)

    for region_name, seed_map in regions.items():
        for seed, t in seed_map.items():
            team_meta[t.name] = (seed, region_name)
        rp, champs = _propagate_region(seed_map)
        for tname, probs in rp.items():
            region_round_probs[tname] = probs
        region_champions[region_name] = champs

    ff_probs = _propagate_final_four(region_champions, ff_matchups)

    round_names = ["R64_win", "R32_win", "S16_win", "E8_win", "F4_win", "CG_win"]
    results = {}

    for tname, r14 in region_round_probs.items():
        full = list(r14) + ff_probs.get(tname, [])
        rp_dict = {}
        for i, rname in enumerate(round_names):
            rp_dict[rname] = full[i] if i < len(full) else 0.0

        eg = 1.0 + sum(full)
        seed, region = team_meta[tname]
        results[tname] = {
            "seed": seed,
            "region": region,
            "expected_games": eg,
            "round_probs": rp_dict,
        }

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Analytical NCAA bracket simulation")
    parser.add_argument("--bracket", type=str, default="data/bracket.json",
                        help="Path to bracket.json")
    parser.add_argument("--kenpom", type=str, required=True,
                        help="Path to KenPom CSV (must have Team, AdjO, AdjD columns)")
    parser.add_argument("--detailed", action="store_true",
                        help="Print full round-by-round probabilities")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to CSV")
    args = parser.parse_args()

    bracket = load_bracket(args.bracket)
    kenpom_df = pd.read_csv(args.kenpom)

    if args.detailed:
        results = calculate_round_probabilities(kenpom_df, bracket)
        rows = []
        for tname, info in sorted(results.items(),
                                    key=lambda x: -x[1]["expected_games"]):
            row = {
                "Team": tname,
                "Seed": info["seed"],
                "Region": info["region"],
                "ExpGames": round(info["expected_games"], 3),
            }
            for rname, p in info["round_probs"].items():
                row[rname] = round(p, 4)
            rows.append(row)
        df = pd.DataFrame(rows)
        print(df.to_string(index=False))
        if args.output:
            df.to_csv(args.output, index=False)
            print(f"\nSaved to {args.output}")
    else:
        expected = calculate_expected_games(kenpom_df, bracket)
        rows = [(name, round(eg, 3)) for name, eg in
                sorted(expected.items(), key=lambda x: -x[1])]
        df = pd.DataFrame(rows, columns=["Team", "ExpectedGames"])
        print(df.to_string(index=False))
        if args.output:
            df.to_csv(args.output, index=False)
            print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
