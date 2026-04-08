"""Cross-year algorithm performance comparison.

Scans archive/<year>/ directories and compares calibration metrics across
seasons. Useful for answering: "Did the algorithm change between year X and
year Y actually improve calibration, or did it just trade one error for another?"

Requires each year to have been processed by analyze_year.py first (so
analysis/calibration.csv and player_residuals.csv exist).

Usage: python src/compare_years.py
"""
import csv
from pathlib import Path
from statistics import mean, stdev


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v, d=0.0):
    try: return float(v) if v not in ("", None) else d
    except ValueError: return d


def compare():
    root = Path(__file__).resolve().parents[1]
    archive = root / "archive"
    if not archive.exists():
        print("No archive directory found.")
        return

    years = sorted(int(p.name) for p in archive.iterdir()
                   if p.is_dir() and p.name.isdigit())
    if not years:
        print("No archived years found.")
        return

    print(f"Found {len(years)} archived year(s): {years}\n")

    # --- Per-year algorithm version ---
    print("=== ALGORITHM VERSIONS ===")
    for y in years:
        ver_path = archive / str(y) / "algorithm_version.txt"
        if ver_path.exists():
            sha = ""
            for line in ver_path.read_text().splitlines():
                if line.startswith("PROJECTIONS_GIT_SHA:"):
                    sha = line.split(":", 1)[1].strip()[:10]
                    break
            print(f"  {y}: {sha}")
    print()

    # --- Calibration trend (avg actual / avg projected, per top-N bucket) ---
    print("=== CALIBRATION TREND (delta % = actual vs projected, lower abs = better) ===")
    print(f"{'top-N':>6} | " + " | ".join(f"{y:>10}" for y in years))
    print("-" * (8 + 13 * len(years)))
    buckets = ["10", "25", "50", "100", "150", "210"]
    for n in buckets:
        row = [f"{n:>6}"]
        for y in years:
            cp = archive / str(y) / "analysis" / "calibration.csv"
            if not cp.exists():
                row.append(f"{'(no data)':>10}")
                continue
            cal = load_csv(cp)
            match = next((c for c in cal if c["top_n"] == n), None)
            row.append(f"{match['pct_error']+'%':>10}" if match else f"{'-':>10}")
        print(" | ".join(row))
    print()

    # --- Per-year MAE and RMSE on player residuals ---
    print("=== ERROR METRICS ===")
    print(f"{'year':>6} | {'n':>5} | {'MAE':>8} | {'RMSE':>8} | {'mean_resid':>11}")
    for y in years:
        rp = archive / str(y) / "analysis" / "player_residuals.csv"
        if not rp.exists():
            continue
        rows = [r for r in load_csv(rp)
                if r.get("matched") == "1" and not r.get("in_tournament_injury")]
        residuals = [to_float(r["residual"]) for r in rows if r["residual"] != ""]
        if not residuals:
            continue
        mae = mean(abs(r) for r in residuals)
        rmse = (mean(r * r for r in residuals)) ** 0.5
        mean_r = mean(residuals)
        print(f"  {y} | {len(residuals):>5} | {mae:>8.1f} | {rmse:>8.1f} | {mean_r:>+11.2f}")
    print()

    # --- Per-team residual trend (only teams that appear 2+ years) ---
    if len(years) >= 2:
        from collections import defaultdict
        team_year_resid = defaultdict(dict)
        for y in years:
            rp = archive / str(y) / "analysis" / "player_residuals.csv"
            if not rp.exists():
                continue
            rows = [r for r in load_csv(rp)
                    if r.get("matched") == "1" and not r.get("in_tournament_injury")]
            by_team = defaultdict(list)
            for r in rows:
                by_team[r["team"]].append(to_float(r["residual"]))
            for t, resids in by_team.items():
                team_year_resid[t][y] = mean(resids)

        recurring = {t: yrs for t, yrs in team_year_resid.items() if len(yrs) >= 2}
        if recurring:
            print(f"=== TEAMS WITH PERSISTENT BIAS (in {len(years)} years) ===")
            print("Avg residual per player, per year. Teams consistently over-")
            print("or under-projected across years are candidates for tuning.")
            print()
            print(f"{'team':<20}" + "".join(f"{y:>10}" for y in years))
            for t in sorted(recurring):
                row = f"{t:<20}"
                for y in years:
                    v = recurring[t].get(y)
                    row += f"{v:>+10.1f}" if v is not None else f"{'-':>10}"
                print(row)
        else:
            print("(No teams appear in 2+ years yet.)")
    else:
        print("(Cross-year team analysis requires 2+ archived years.)")


if __name__ == "__main__":
    compare()
