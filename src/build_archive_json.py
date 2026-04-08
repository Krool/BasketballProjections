"""Convert archive/<year>/ CSVs into a single JSON bundle for the website.

Outputs:
  docs/archive/<year>.json   — everything the SPA needs for one year
  docs/archive/index.json    — list of available years with headline stats

Run after analyze_year.py. The website's History Mode fetches these files.

Usage: python src/build_archive_json.py 2026
       python src/build_archive_json.py --all
"""
import csv
import json
import sys
from pathlib import Path


def load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(v, d=0):
    try: return int(v) if v not in ("", None) else d
    except (ValueError, TypeError): return d


def to_float(v, d=0.0):
    try: return float(v) if v not in ("", None) else d
    except (ValueError, TypeError): return d


def build_year(year: int, root: Path):
    yroot = root / "archive" / str(year)
    if not yroot.exists():
        print(f"  no archive for {year}")
        return None

    players = load_csv(yroot / "actual" / "player_results.csv")
    picks = load_csv(yroot / "actual" / "draft_picks.csv")
    totals = load_csv(yroot / "actual" / "entry_totals.csv")
    bracket = json.load(open(yroot / "actual" / "bracket_outcome.json"))
    proj = load_csv(yroot / "projections_final.csv")
    residuals = load_csv(yroot / "analysis" / "player_residuals.csv")
    calibration = load_csv(yroot / "analysis" / "calibration.csv")
    bias_seed = load_csv(yroot / "analysis" / "bias_by_seed.csv")
    draft_eff = load_csv(yroot / "analysis" / "draft_efficiency.csv")
    entry_pm = load_csv(yroot / "analysis" / "entry_post_mortem.csv")

    # Index projections for join
    proj_idx = {(p["player"], p["team"]): p for p in proj}

    # Build picks with hindsight: each pick gets its actual_pts and projected
    pick_rows = []
    actual_idx = {(a["player"], a["team"]): a for a in players}
    for pk in picks:
        a = actual_idx.get((pk["player"], pk["team"]))
        p = proj_idx.get((pk["player"], pk["team"]))
        proj_total = (to_float(p.get("ppg")) * to_float(p.get("expected_games"))) if p else 0
        pick_rows.append({
            "pick": to_int(pk["pick"]),
            "round": to_int(pk["round"]),
            "entry": pk["entry"],
            "player": pk["player"],
            "team": pk["team"],
            "espn_id": pk.get("espn_id", ""),
            "actual_pts": to_int(a["total_points"]) if a else 0,
            "games_played": to_int(a["games_played"]) if a else 0,
            "proj_total": round(proj_total, 1),
            "proj_rank": to_int(p.get("rank")) if p else None,
            "residual": round(to_int(a["total_points"]) - proj_total, 1) if a and proj_total else None,
            "alive": to_int(a.get("alive")) if a else 0,
            "in_tournament_injury": (a or {}).get("in_tournament_injury", ""),
        })

    # Compute actual_rank within the drafted pool: rank by actual points desc.
    # slots_change = draft_pick - actual_rank.
    #   positive = drafted lower than they finished (riser / steal)
    #   negative = drafted higher than they finished (faller / bust)
    # In-tournament injuries are excluded from ranking (assigned actual_rank=null)
    # so they don't pollute the riser/faller lists.
    rankable = [r for r in pick_rows if not r["in_tournament_injury"]]
    rankable.sort(key=lambda r: (-r["actual_pts"], r["pick"]))  # tiebreak: earlier pick wins
    rank_map = {(r["player"], r["team"]): i + 1 for i, r in enumerate(rankable)}
    for r in pick_rows:
        if r["in_tournament_injury"]:
            r["actual_rank"] = None
            r["slots_change"] = None
        else:
            ar = rank_map.get((r["player"], r["team"]))
            r["actual_rank"] = ar
            r["slots_change"] = (r["pick"] - ar) if ar is not None else None

    # Standings
    standings = []
    for t in totals:
        standings.append({
            "entry": t["entry"],
            "total": to_int(t["total"]),
            "r64": to_int(t["r64"]),
            "r32": to_int(t["r32"]),
            "s16": to_int(t["s16"]),
            "e8": to_int(t["e8"]),
            "f4": to_int(t["f4"]),
            "championship": to_int(t["championship"]),
            "players_left": to_int(t["players_left"]),
        })
    standings.sort(key=lambda r: -r["total"])
    for i, s in enumerate(standings):
        s["rank"] = i + 1

    # Top steals & busts
    matched = [r for r in residuals if r.get("matched") == "1" and not r.get("in_tournament_injury")]
    for r in matched:
        r["_resid"] = to_float(r["residual"])
    top_steals = sorted(matched, key=lambda r: -r["_resid"])[:15]
    top_busts = sorted(matched, key=lambda r: r["_resid"])[:15]

    def clean(r):
        return {k: v for k, v in r.items() if not k.startswith("_")}

    bundle = {
        "year": year,
        "champion": bracket.get("champion"),
        "finalists": bracket.get("finalists", []),
        "final_four": bracket.get("final_four", []),
        "elite_eight": bracket.get("elite_eight", []),
        "sweet_sixteen": bracket.get("sweet_sixteen", []),
        "round_of_32": bracket.get("round_of_32", []),
        "games": bracket.get("games", []),
        "standings": standings,
        "winning_entry": standings[0]["entry"] if standings else None,
        "winning_score": standings[0]["total"] if standings else None,
        "picks": pick_rows,
        "residuals": [clean(r) for r in matched],
        "top_steals": [clean(r) for r in top_steals],
        "top_busts": [clean(r) for r in top_busts],
        "calibration": calibration,
        "bias_by_seed": bias_seed,
        "draft_efficiency": draft_eff,
        "entry_post_mortem": entry_pm,
        "n_drafted": len(players),
        "n_in_tournament_injuries": sum(1 for p in players if p.get("in_tournament_injury")),
    }
    return bundle


def write_year(year: int, bundle: dict, root: Path):
    out_dir = root / "docs" / "archive"
    out_dir.mkdir(exist_ok=True, parents=True)
    out_path = out_dir / f"{year}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, separators=(",", ":"))
    size_kb = out_path.stat().st_size / 1024
    print(f"  wrote {out_path.name} ({size_kb:.0f} KB)")

    # Also emit a players.json-shaped file so the live draft board can load
    # an archived year's projections directly via the existing UI.
    yroot = root / "archive" / str(year)
    proj = load_csv(yroot / "projections_final.csv")
    players_payload = []
    for p in proj:
        ppg = to_float(p.get("ppg"))
        eg = to_float(p.get("expected_games"))
        players_payload.append({
            "rank": to_int(p.get("rank")),
            "player": p.get("player"),
            "team": p.get("team"),
            "seed": to_int(p.get("seed")),
            "region": p.get("region"),
            "ppg": ppg,
            "expected_games": eg,
            "injury_status": p.get("injury_status") or "HEALTHY",
            "projected_points": round(ppg * eg, 1),
            "espn_id": p.get("espn_id", ""),
        })
    players_out = {
        "generated_at": f"{year}-archive",
        "players": players_payload,
        "_archive_year": year,
    }
    p_path = out_dir / f"{year}_players.json"
    with open(p_path, "w", encoding="utf-8") as f:
        json.dump(players_out, f, separators=(",", ":"))
    print(f"  wrote {p_path.name} ({p_path.stat().st_size/1024:.0f} KB)")


def write_index(years_built: list, root: Path):
    out_dir = root / "docs" / "archive"
    out_dir.mkdir(exist_ok=True, parents=True)
    index = {"years": []}
    for year, bundle in years_built:
        index["years"].append({
            "year": year,
            "champion": bundle.get("champion"),
            "winning_entry": bundle.get("winning_entry"),
            "winning_score": bundle.get("winning_score"),
            "n_drafted": bundle.get("n_drafted"),
        })
    index["years"].sort(key=lambda r: -r["year"])
    with open(out_dir / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"  wrote index.json ({len(index['years'])} years)")


def main():
    root = Path(__file__).resolve().parents[1]
    args = sys.argv[1:]
    if not args or args[0] == "--all":
        years = sorted(int(p.name) for p in (root / "archive").iterdir()
                       if p.is_dir() and p.name.isdigit())
    else:
        years = [int(a) for a in args]

    print(f"Building archive JSON for years: {years}")
    built = []
    for y in years:
        bundle = build_year(y, root)
        if bundle:
            write_year(y, bundle, root)
            built.append((y, bundle))
    write_index(built, root)


if __name__ == "__main__":
    main()
