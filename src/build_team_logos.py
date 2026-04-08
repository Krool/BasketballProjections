"""Generate docs/team_logos.json from src/scrape_players_espn.py's ESPN_TEAM_IDS.

Run this whenever ESPN_TEAM_IDS is updated. The website fetches this file
on load so the team-logo map is single-sourced from the Python scraper.

Usage: python src/build_team_logos.py
"""
import json
from pathlib import Path

from scrape_players_espn import ESPN_TEAM_IDS


def main():
    root = Path(__file__).resolve().parents[1]
    out_path = root / "docs" / "team_logos.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ESPN_TEAM_IDS, f, indent=2, sort_keys=True)
    print(f"Wrote {len(ESPN_TEAM_IDS)} teams → {out_path}")


if __name__ == "__main__":
    main()
