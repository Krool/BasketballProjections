"""Post-mortem analysis of a draft year.

Joins archived projections against actual tournament outcomes and produces:
  - per-player residuals (projected vs actual points & games)
  - per-team round-reached vs projected wins
  - calibration: do top-N projections actually score more?
  - bias by seed, region, injury status
  - biggest misses leaderboard
  - draft value: actual_pts vs draft pick

Usage: python src/analyze_year.py 2026
Outputs: archive/<year>/analysis/*.csv and a printed summary.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

# Import canonical field names so a column rename in the archive CSV
# breaks at import time instead of producing silently-wrong analysis.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_schema import (
    COL_PLAYER, COL_TEAM, COL_ENTRY, COL_PICK, COL_ESPN_ID,
    COL_GAMES_PLAYED, COL_TOTAL_POINTS, COL_ALIVE, COL_IN_TOURNAMENT_INJURY,
    BO_CHAMPION, BO_FINALISTS, BO_FINAL_FOUR, BO_ELITE_EIGHT,
    BO_SWEET_SIXTEEN, BO_ROUND_OF_32,
)


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(v, default=0):
    try:
        return int(v) if v not in ("", None) else default
    except ValueError:
        return default


def to_float(v, default=0.0):
    try:
        return float(v) if v not in ("", None) else default
    except ValueError:
        return default


def analyze(year: int):
    root = Path(__file__).resolve().parents[1]
    yroot = root / "archive" / str(year)
    proj = load(yroot / "projections_final.csv")
    actual = load(yroot / "actual" / "player_results.csv")
    picks = load(yroot / "actual" / "draft_picks.csv")
    bracket = json.load(open(yroot / "actual" / "bracket_outcome.json"))
    out = yroot / "analysis"
    out.mkdir(exist_ok=True)

    # --- Index projections by (player, team) ---
    proj_idx = {(p["player"], p["team"]): p for p in proj}

    # --- Per-player residuals (only drafted players) ---
    rows = []
    for a in actual:
        key = (a["player"], a["team"])
        p = proj_idx.get(key)
        actual_pts = to_int(a[COL_TOTAL_POINTS])
        actual_games = to_int(a[COL_GAMES_PLAYED])
        if p is None:
            rows.append({
                "player": a["player"], "team": a["team"], "entry": a[COL_ENTRY],
                "proj_rank": "", "proj_ppg": "", "proj_games": "", "proj_total": "",
                "actual_pts": actual_pts, "actual_games": actual_games,
                "residual": "", "pct_error": "", "matched": 0,
            })
            continue
        proj_ppg = to_float(p.get("ppg"))
        proj_games = to_float(p.get("expected_games"))
        proj_total = proj_ppg * proj_games
        residual = actual_pts - proj_total
        pct_err = (residual / proj_total * 100) if proj_total else ""
        rows.append({
            "player": a["player"], "team": a["team"], "entry": a[COL_ENTRY],
            "proj_rank": p.get("rank", ""),
            "proj_ppg": round(proj_ppg, 2),
            "proj_games": round(proj_games, 2),
            "proj_total": round(proj_total, 1),
            "actual_pts": actual_pts,
            "actual_games": actual_games,
            "residual": round(residual, 1),
            "pct_error": round(pct_err, 1) if pct_err != "" else "",
            "matched": 1,
            "seed": p.get("seed", ""),
            "region": p.get("region", ""),
            "injury_status": p.get("injury_status", ""),
            "in_tournament_injury": a.get(COL_IN_TOURNAMENT_INJURY, ""),
        })

    # Write per-player residuals
    fields = ["player", "team", "entry", "seed", "region", "injury_status",
              "in_tournament_injury",
              "proj_rank", "proj_ppg", "proj_games", "proj_total",
              "actual_pts", "actual_games", "residual", "pct_error", "matched"]
    with open(out / "player_residuals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    # --- In-tournament injuries: separated up front so all aggregates exclude them ---
    matched_all = [r for r in rows if r["matched"] == 1]
    in_tourney_injured = [r for r in matched_all if r.get(COL_IN_TOURNAMENT_INJURY)]
    matched = [r for r in matched_all if not r.get(COL_IN_TOURNAMENT_INJURY)]
    matched_sorted = sorted(matched, key=lambda r: -r["proj_total"])
    calibration = []
    for n in (10, 25, 50, 100, 150, 210):
        topn = matched_sorted[:n]
        avg_proj = mean(r["proj_total"] for r in topn)
        avg_actual = mean(r["actual_pts"] for r in topn)
        calibration.append({
            "top_n": n,
            "avg_projected": round(avg_proj, 1),
            "avg_actual": round(avg_actual, 1),
            "delta": round(avg_actual - avg_proj, 1),
            "pct_error": round((avg_actual - avg_proj) / avg_proj * 100, 1) if avg_proj else "",
        })
    with open(out / "calibration.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["top_n", "avg_projected", "avg_actual", "delta", "pct_error"])
        w.writeheader()
        w.writerows(calibration)

    # --- Bias by seed ---
    by_seed = defaultdict(list)
    for r in matched:
        if r.get("seed"):
            by_seed[str(r["seed"])].append(r)
    seed_rows = []
    for seed, rs in sorted(by_seed.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 99):
        seed_rows.append({
            "seed": seed,
            "n_players": len(rs),
            "avg_projected": round(mean(r["proj_total"] for r in rs), 1),
            "avg_actual": round(mean(r["actual_pts"] for r in rs), 1),
            "avg_residual": round(mean(r["residual"] for r in rs), 1),
        })
    with open(out / "bias_by_seed.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["seed", "n_players", "avg_projected", "avg_actual", "avg_residual"])
        w.writeheader()
        w.writerows(seed_rows)

    # --- Bias by injury status ---
    by_inj = defaultdict(list)
    for r in matched:
        by_inj[r.get("injury_status") or "UNKNOWN"].append(r)
    inj_rows = []
    for status, rs in sorted(by_inj.items()):
        inj_rows.append({
            "injury_status": status,
            "n_players": len(rs),
            "avg_projected": round(mean(r["proj_total"] for r in rs), 1),
            "avg_actual": round(mean(r["actual_pts"] for r in rs), 1),
            "avg_residual": round(mean(r["residual"] for r in rs), 1),
        })
    with open(out / "bias_by_injury.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["injury_status", "n_players", "avg_projected", "avg_actual", "avg_residual"])
        w.writeheader()
        w.writerows(inj_rows)

    # --- Team round-reached vs projected wins ---
    # Map team -> rounds won (count of rounds where team appears in bracket_outcome)
    team_rounds = defaultdict(int)
    round_keys = [
        (BO_ROUND_OF_32, 1), (BO_SWEET_SIXTEEN, 2), (BO_ELITE_EIGHT, 3),
        (BO_FINAL_FOUR, 4), (BO_FINALISTS, 5), (BO_CHAMPION, 6),
    ]
    for key, _ in round_keys:
        teams = bracket.get(key, [])
        if isinstance(teams, str):
            teams = [teams]
        for t in teams:
            team_rounds[t] += 1
    # Projected wins per team (avg expected_games - 1, since first game is given)
    proj_wins_by_team = defaultdict(list)
    for p in proj:
        proj_wins_by_team[p["team"]].append(to_float(p.get("expected_games")))
    team_rows = []
    all_teams = set(team_rounds) | set(proj_wins_by_team)
    for t in sorted(all_teams):
        gms = proj_wins_by_team.get(t, [])
        avg_g = round(mean(gms), 2) if gms else ""
        team_rows.append({
            "team": t,
            "actual_wins": team_rounds.get(t, 0),
            "avg_proj_games_per_player": avg_g,
        })
    with open(out / "team_round_vs_projection.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["team", "actual_wins", "avg_proj_games_per_player"])
        w.writeheader()
        w.writerows(team_rows)

    # --- Biggest misses (clean set; injuries already excluded) ---
    biggest_under = sorted(matched, key=lambda r: r["residual"])[:15]
    biggest_over = sorted(matched, key=lambda r: -r["residual"])[:15]

    # --- Draft value (actual pts vs pick number) ---
    pick_idx = {(p["player"], p["entry"]): int(p[COL_PICK]) for p in picks}
    value_rows = []
    for a in actual:
        pick = pick_idx.get((a["player"], a[COL_ENTRY]))
        if pick is None:
            continue
        value_rows.append({
            "pick": pick,
            "player": a["player"],
            "team": a["team"],
            "entry": a[COL_ENTRY],
            "actual_pts": to_int(a[COL_TOTAL_POINTS]),
        })
    value_rows.sort(key=lambda r: r["pick"])
    # Steals: high actual relative to pick number (low pick = early)
    # Compute z within pick deciles instead — simple: rank by actual_pts vs pick
    for r in value_rows:
        r["value_score"] = round(r["actual_pts"] - (210 - r["pick"]) * 0.5, 1)
    steals = sorted(value_rows, key=lambda r: -r["value_score"])[:15]
    busts = sorted(value_rows, key=lambda r: r["value_score"])[:15]
    with open(out / "draft_value.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pick", "player", "team", "entry", "actual_pts", "value_score"])
        w.writeheader()
        w.writerows(value_rows)

    # --- Draft efficiency: did entries that followed projections do better? ---
    # For each entry, compare actual score against two benchmarks:
    #   (a) algo_score: simulate the draft where each entry takes the highest
    #       *projected* player still available at their pick. This is "what
    #       would have happened if everyone followed the algorithm."
    #   (b) actual_rank_score: simulate where players are taken in *actual*
    #       point order (best actual scorer at pick 1, etc.). NOT a true
    #       ceiling — just a benchmark showing what each pick slot would
    #       have yielded under perfect retrospective ordering. An entry CAN
    #       beat this if their actual picks outperformed the top-N-by-pick
    #       baseline (Lucas did this in 2026).
    # actual - algo_score = how much they deviated from the algo and won/lost
    actual_pts_idx = {(a["player"], a["team"]): to_int(a[COL_TOTAL_POINTS])
                      for a in actual}
    proj_total_idx = {(p["player"], p["team"]):
                      to_float(p.get("ppg")) * to_float(p.get("expected_games"))
                      for p in proj}

    # Sort all picks by global pick order
    picks_ordered = sorted(picks, key=lambda p: int(p[COL_PICK]))

    # Simulate algo-following draft: at each pick, the entry on the clock takes
    # the highest projected player still available
    pool_proj = sorted(proj, key=lambda p: -proj_total_idx.get((p["player"], p["team"]), 0))
    pool_actual = sorted(proj, key=lambda p: -actual_pts_idx.get((p["player"], p["team"]), 0))
    available_proj = [(p["player"], p["team"]) for p in pool_proj]
    available_actual = [(p["player"], p["team"]) for p in pool_actual]

    algo_picks_per_entry = defaultdict(list)
    actual_rank_picks_per_entry = defaultdict(list)
    for pk in picks_ordered:
        entry = pk[COL_ENTRY]
        if available_proj:
            choice = available_proj.pop(0)
            algo_picks_per_entry[entry].append(choice)
        if available_actual:
            choice2 = available_actual.pop(0)
            actual_rank_picks_per_entry[entry].append(choice2)

    # Score each simulated draft using actual points
    eff_rows = []
    actual_by_entry = defaultdict(int)
    for a in actual:
        actual_by_entry[a[COL_ENTRY]] += to_int(a[COL_TOTAL_POINTS])
    for entry in sorted(actual_by_entry):
        algo_score = sum(actual_pts_idx.get(k, 0) for k in algo_picks_per_entry[entry])
        actual_rank_score = sum(actual_pts_idx.get(k, 0) for k in actual_rank_picks_per_entry[entry])
        actual_score = actual_by_entry[entry]
        eff_rows.append({
            "entry": entry,
            "actual_score": actual_score,
            "algo_score": algo_score,
            "actual_rank_score": actual_rank_score,
            "deviation_from_algo": actual_score - algo_score,
            "vs_actual_rank": actual_score - actual_rank_score,
        })
    eff_rows.sort(key=lambda r: -r["actual_score"])
    with open(out / "draft_efficiency.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["entry", "actual_score", "algo_score", "actual_rank_score",
                                          "deviation_from_algo", "vs_actual_rank"])
        w.writeheader()
        w.writerows(eff_rows)

    # --- Per-entry post-mortem (skill vs variance) ---
    entry_resids = defaultdict(list)
    for r in matched:
        entry_resids[r["entry"]].append(r["residual"])
    entry_pm_rows = []
    for entry, resids in entry_resids.items():
        n = len(resids)
        mae = sum(abs(r) for r in resids) / n if n else 0
        mean_r = sum(resids) / n if n else 0
        # Hit rate: how many picks beat expectation
        hits = sum(1 for r in resids if r > 0)
        entry_pm_rows.append({
            "entry": entry,
            "n_picks": n,
            "mae": round(mae, 1),
            "mean_residual": round(mean_r, 1),
            "hit_rate": round(hits / n * 100, 1) if n else 0,
        })
    entry_pm_rows.sort(key=lambda r: -r["mean_residual"])
    with open(out / "entry_post_mortem.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["entry", "n_picks", "mae", "mean_residual", "hit_rate"])
        w.writeheader()
        w.writerows(entry_pm_rows)

    # --- Print summary ---
    print(f"=== {year} POST-MORTEM ===")
    print(f"Champion: {bracket['champion']}")
    print(f"Players matched to projections: {len(matched_all)} / {len(actual)}")
    if in_tourney_injured:
        print(f"In-tournament injuries excluded from all aggregates: {len(in_tourney_injured)}")
        for r in in_tourney_injured:
            print(f"  - {r['player']} ({r['team']}) proj={r['proj_total']} actual={r['actual_pts']} — {r['in_tournament_injury']}")
        print(f"Clean sample for calibration/bias/misses: {len(matched)}")
    unmatched = [r for r in rows if r["matched"] == 0]
    if unmatched:
        print(f"Unmatched (no projection found):")
        for u in unmatched:
            print(f"  - {u['player']} ({u['team']}, drafted by {u['entry']})")
    print()
    print("CALIBRATION (avg projected vs actual):")
    for c in calibration:
        print(f"  Top {c['top_n']:>3}: proj={c['avg_projected']:>6} actual={c['avg_actual']:>6} delta={c['delta']:+.1f} ({c['pct_error']:+.1f}%)")
    print()
    print("BIAS BY SEED (avg residual = actual - projected):")
    for s in seed_rows:
        print(f"  Seed {s['seed']:>2}: n={s['n_players']:>3}  proj={s['avg_projected']:>6}  actual={s['avg_actual']:>6}  resid={s['avg_residual']:+.1f}")
    print()
    print("BIAS BY INJURY STATUS:")
    for s in inj_rows:
        print(f"  {s['injury_status']:<15} n={s['n_players']:>3}  proj={s['avg_projected']:>6}  actual={s['avg_actual']:>6}  resid={s['avg_residual']:+.1f}")
    print()
    print("BIGGEST UNDER-PROJECTED (actual >> projection):")
    for r in biggest_over[:10]:
        print(f"  {r['player']:<25} {r['team']:<15} proj={r['proj_total']:>6}  actual={r['actual_pts']:>4}  resid={r['residual']:+.1f}")
    print()
    print("BIGGEST OVER-PROJECTED (actual << projection):")
    for r in biggest_under[:10]:
        print(f"  {r['player']:<25} {r['team']:<15} proj={r['proj_total']:>6}  actual={r['actual_pts']:>4}  resid={r['residual']:+.1f}")
    print()
    print("TOP 10 DRAFT STEALS (high actual relative to pick number):")
    for r in steals[:10]:
        print(f"  pick {r['pick']:>3}: {r['player']:<25} {r['team']:<15} actual={r['actual_pts']:>4} (drafted by {r['entry']})")
    print()
    print("TOP 10 DRAFT BUSTS:")
    for r in busts[:10]:
        print(f"  pick {r['pick']:>3}: {r['player']:<25} {r['team']:<15} actual={r['actual_pts']:>4} (drafted by {r['entry']})")
    print()
    print()
    print("DRAFT EFFICIENCY:")
    print("  actual = real score; algo = simulated score if entry took top-projected at each pick;")
    print("  rank_base = simulated score if top-actual went in pick order (a benchmark, NOT a ceiling)")
    print(f"  {'entry':<15} {'actual':>7} {'algo':>7} {'rank_base':>10} {'vs_algo':>8} {'vs_rank':>8}")
    for r in eff_rows:
        print(f"  {r['entry']:<15} {r['actual_score']:>7} {r['algo_score']:>7} "
              f"{r['actual_rank_score']:>10} {r['deviation_from_algo']:>+8} "
              f"{r['vs_actual_rank']:>+8}")
    print()
    print("ENTRY POST-MORTEM (per-pick MAE, hit rate vs projection):")
    print(f"  {'entry':<15} {'n':>3} {'MAE':>6} {'mean_resid':>11} {'hit%':>6}")
    for r in entry_pm_rows:
        print(f"  {r['entry']:<15} {r['n_picks']:>3} {r['mae']:>6} "
              f"{r['mean_residual']:>+11} {r['hit_rate']:>5}%")
    print()
    print(f"Wrote analysis files to {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Post-mortem analysis of a draft year. "
                    "Joins archived projections against actual tournament outcomes "
                    "and writes residuals, calibration, bias, and draft efficiency CSVs "
                    "to archive/<year>/analysis/."
    )
    ap.add_argument("year", type=int, nargs="?", default=2026,
                    help="Draft year to analyze (default: 2026)")
    args = ap.parse_args()
    analyze(args.year)
