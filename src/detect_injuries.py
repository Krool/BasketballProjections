"""Post-tournament injury candidate scanner.

Run once after the tournament. Identifies drafted players whose actual results
suggest an in-tournament injury (DNP, sudden production cliff, or massive
underperformance vs projection). Outputs a candidates CSV for manual review.

After reviewing the candidates, manually populate the `in_tournament_injury`
column in archive/<year>/actual/player_results.csv for confirmed cases. Then
re-run analyze_year.py to exclude them from algorithm calibration stats.

Usage: python src/detect_injuries.py 2026
"""
import csv
import json
import sys
from pathlib import Path

# Field name constants — single source of truth lives in archive_schema.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_schema import (
    COL_PLAYER, COL_TEAM, COL_ENTRY,
    COL_GAMES_PLAYED, COL_TOTAL_POINTS, COL_IN_TOURNAMENT_INJURY,
    ROUND_COLS,
    BO_ROUND_OF_32, BO_SWEET_SIXTEEN, BO_ELITE_EIGHT,
    BO_FINAL_FOUR, BO_FINALISTS,
)

# ===== Heuristic thresholds for injury detection =====
# These are calibrated against 2026 data (Joshua Jefferson + Tyler Bilodeau
# both surface, all 1-and-done false positives are filtered). Tune cautiously
# — false positives create review fatigue, false negatives let injuries
# pollute calibration aggregates.
DNP_CONFIDENCE = 50               # weight for "missed N rounds entirely"
CLIFF_CONFIDENCE = 50             # weight for "produced then went cold"
CLIFF_MIN_PRODUCTION_PTS = 5      # how many points counts as "produced"
CLIFF_MIN_ZEROS = 2               # require 2+ zeros after producing
CLIFF_MIN_PLAYED_ROUNDS = 3       # need 3+ rounds of data to spot a cliff
UNDERPERF_CONFIDENCE = 40         # weight for "actual << projection"
UNDERPERF_MIN_PROJ = 30           # only flag if proj was meaningful (≥30 pts)
UNDERPERF_RATIO = 0.25            # actual ≤ 25% of projection
UNDERPERF_MIN_TEAM_GAMES = 2      # exclude 1-and-done teams (too noisy)


def to_int(v, d=0):
    try: return int(v) if v not in ("", None) else d
    except ValueError: return d

def to_float(v, d=0.0):
    try: return float(v) if v not in ("", None) else d
    except ValueError: return d


def detect(year: int):
    root = Path(__file__).resolve().parents[1]
    yroot = root / "archive" / str(year)
    players = list(csv.DictReader(open(yroot / "actual" / "player_results.csv")))
    proj = {(p[COL_PLAYER], p[COL_TEAM]): p
            for p in csv.DictReader(open(yroot / "projections_final.csv"))}
    bracket = json.load(open(yroot / "actual" / "bracket_outcome.json"))

    def team_rounds(team):
        g = 1
        for k in [BO_ROUND_OF_32, BO_SWEET_SIXTEEN, BO_ELITE_EIGHT,
                  BO_FINAL_FOUR, BO_FINALISTS]:
            if team in bracket.get(k, []):
                g += 1
        return g

    candidates = []

    for p in players:
        team_g = team_rounds(p[COL_TEAM])
        played_g = to_int(p[COL_GAMES_PLAYED])
        actual = to_int(p[COL_TOTAL_POINTS])
        scores = [p[r] for r in ROUND_COLS[:team_g]]  # only rounds team played

        signals = []
        confidence = 0

        # Signal 1: DNP — fewer games played than team
        missed = team_g - played_g
        if missed > 0:
            signals.append(f"DNP {missed} round(s)")
            confidence += DNP_CONFIDENCE

        # Signal 2: Sudden cliff — sustained zeros after producing.
        nums = [to_int(s) for s in scores if s != ""]
        if len(nums) >= CLIFF_MIN_PLAYED_ROUNDS:
            had_production = False
            cliff_zeros = 0
            for v in nums:
                if v >= CLIFF_MIN_PRODUCTION_PTS: had_production = True
                elif had_production and v == 0: cliff_zeros += 1
            if had_production and cliff_zeros >= CLIFF_MIN_ZEROS:
                signals.append(f"cliff: {cliff_zeros} zero round(s) after producing")
                confidence += CLIFF_CONFIDENCE

        # Signal 3: Massive underperformance vs projection.
        pr = proj.get((p[COL_PLAYER], p[COL_TEAM]))
        if pr and team_g >= UNDERPERF_MIN_TEAM_GAMES:
            proj_total = to_float(pr.get("ppg")) * to_float(pr.get("expected_games"))
            if proj_total >= UNDERPERF_MIN_PROJ and actual <= proj_total * UNDERPERF_RATIO:
                signals.append(f"actual {actual} vs proj {proj_total:.0f} ({actual/proj_total*100:.0f}%)")
                confidence += UNDERPERF_CONFIDENCE

        if signals:
            candidates.append({
                "player": p[COL_PLAYER],
                "team": p[COL_TEAM],
                "entry": p[COL_ENTRY],
                "team_games": team_g,
                "player_games": played_g,
                "actual_pts": actual,
                "round_scores": ",".join(scores),
                "signals": "; ".join(signals),
                "confidence": confidence,
                "current_flag": p.get(COL_IN_TOURNAMENT_INJURY, ""),
            })

    candidates.sort(key=lambda c: -c["confidence"])
    out_path = yroot / "actual" / "injury_candidates.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(candidates[0].keys()) if candidates else
                           ["player", "team", "entry", "signals", "confidence"])
        w.writeheader()
        w.writerows(candidates)

    print(f"Found {len(candidates)} injury candidates (sorted by confidence):")
    print(f"{'conf':>4}  {'player':<25} {'team':<15} {'rounds':<18} signals")
    for c in candidates:
        print(f"  {c['confidence']:>2}  {c['player']:<25} {c['team']:<15} "
              f"{c['round_scores']:<18} {c['signals']}")
    print()
    print(f"Wrote {out_path}")
    print(f"Review the list, then populate the `in_tournament_injury` column in")
    print(f"player_results.csv for confirmed cases. Re-run analyze_year.py after.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Heuristic scanner for in-tournament injury candidates. "
                    "Reads archive/<year>/actual/player_results.csv and flags players "
                    "by DNP, sustained-zero cliff, or massive underperformance signals. "
                    "Writes injury_candidates.csv for manual review."
    )
    ap.add_argument("year", type=int, nargs="?", default=2026,
                    help="Draft year to scan (default: 2026)")
    args = ap.parse_args()
    detect(args.year)
