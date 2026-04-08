"""Freeze the current data/ + output/ state into archive/<year>/ for posterity.

Run this just before draft day each year to capture the projection inputs and
the projection output that will be used for drafting. After the tournament,
populate archive/<year>/actual/ with player_results.csv, draft_picks.csv,
entry_totals.csv, bracket_outcome.json, then run analyze_year.py.

Usage: python src/snapshot_year.py 2027 [--notes "tweaked surge factor"]
"""
import argparse
import shutil
import subprocess
from pathlib import Path
from datetime import date


def snapshot(year: int, notes: str = ""):
    root = Path(__file__).resolve().parents[1]
    yroot = root / "archive" / str(year)
    (yroot / "inputs").mkdir(parents=True, exist_ok=True)
    (yroot / "actual").mkdir(parents=True, exist_ok=True)
    (yroot / "analysis").mkdir(parents=True, exist_ok=True)

    # Copy projection output
    shutil.copy(root / "output" / "projections.csv",
                yroot / "projections_final.csv")

    # Copy inputs
    inputs = {
        "kenpom.csv": "kenpom.csv",
        "injuries_combined.csv": "injuries.csv",
        "bracket.json": "bracket.json",
    }
    for src, dst in inputs.items():
        s = root / "data" / src
        if s.exists():
            shutil.copy(s, yroot / "inputs" / dst)

    # Capture git SHA + commit message
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    msg = subprocess.check_output(["git", "log", "-1", "--format=%s"], cwd=root).decode().strip()

    (yroot / "algorithm_version.txt").write_text(
        f"YEAR: {year}\n"
        f"SNAPSHOT_DATE: {date.today().isoformat()}\n"
        f"PROJECTIONS_GIT_SHA: {sha}\n"
        f"PROJECTIONS_GIT_DESC: {msg}\n"
        f"\nNOTES:\n{notes or '(none)'}\n"
        f"\nINPUT SNAPSHOTS (in inputs/):\n"
        f"- kenpom.csv\n- injuries.csv\n- bracket.json\n"
        f"\nAfter the tournament, populate actual/ then run:\n"
        f"  python src/analyze_year.py {year}\n"
    )
    print(f"Snapshot written to {yroot}")
    print(f"  git: {sha[:10]} — {msg}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("--notes", default="")
    args = ap.parse_args()
    snapshot(args.year, args.notes)
