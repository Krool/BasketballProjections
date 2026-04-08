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
    proj = {(p["player"], p["team"]): p
            for p in csv.DictReader(open(yroot / "projections_final.csv"))}
    bracket = json.load(open(yroot / "actual" / "bracket_outcome.json"))

    def team_rounds(team):
        g = 1
        for k in ["round_of_32", "sweet_sixteen", "elite_eight",
                  "final_four", "finalists"]:
            if team in bracket.get(k, []):
                g += 1
        return g

    rounds = ["r64", "r32", "s16", "e8", "f4", "championship"]
    candidates = []

    for p in players:
        team_g = team_rounds(p["team"])
        played_g = to_int(p["games_played"])
        actual = to_int(p["total_points"])
        scores = [p[r] for r in rounds[:team_g]]  # only rounds team played

        signals = []
        confidence = 0

        # Signal 1: DNP — fewer games played than team
        missed = team_g - played_g
        if missed > 0:
            signals.append(f"DNP {missed} round(s)")
            confidence += 50

        # Signal 2: Sudden cliff — sustained zeros after producing.
        # Require 2+ zero rounds (a single zero in the team's final round is
        # often just a blowout/upset loss, not an injury).
        nums = [to_int(s) for s in scores if s != ""]
        if len(nums) >= 3:
            had_production = False
            cliff_zeros = 0
            for v in nums:
                if v >= 5: had_production = True
                elif had_production and v == 0: cliff_zeros += 1
            if had_production and cliff_zeros >= 2:
                signals.append(f"cliff: {cliff_zeros} zero round(s) after producing")
                confidence += 50

        # Signal 3: Massive underperformance vs projection.
        # Require team to have played 2+ rounds — single-game samples are too
        # noisy (a 7-seed losing in R64 isn't evidence of injury).
        pr = proj.get((p["player"], p["team"]))
        if pr and team_g >= 2:
            proj_total = to_float(pr.get("ppg")) * to_float(pr.get("expected_games"))
            if proj_total >= 30 and actual <= proj_total * 0.25:
                signals.append(f"actual {actual} vs proj {proj_total:.0f} ({actual/proj_total*100:.0f}%)")
                confidence += 40

        if signals:
            candidates.append({
                "player": p["player"],
                "team": p["team"],
                "entry": p["entry"],
                "team_games": team_g,
                "player_games": played_g,
                "actual_pts": actual,
                "round_scores": ",".join(scores),
                "signals": "; ".join(signals),
                "confidence": confidence,
                "current_flag": p.get("in_tournament_injury", ""),
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
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    detect(year)
