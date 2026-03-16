"""
Parse raw KenPom data from a continuous string into structured CSV files.

The raw data is tab-separated with carriage returns (\\r) separating team entries
(no standard newlines between teams). Each team entry has 21 tab-separated fields:
{rank}\\t{Team Name [Seed]}\\t{Conf}\\t{W-L}\\t{NetRtg}\\t{ORtg}\\t{ORtg_rank}\\t
{DRtg}\\t{DRtg_rank}\\t{AdjT}\\t{AdjT_rank}\\t{Luck}\\t{Luck_rank}\\t
{SOS_NetRtg}\\t{SOS_NetRtg_rank}\\t{SOS_ORtg}\\t{SOS_ORtg_rank}\\t
{SOS_DRtg}\\t{SOS_DRtg_rank}\\t{NCSOS_NetRtg}\\t{NCSOS_rank}

Header rows repeat every ~40 teams and contain "Strength of Schedule".
"""

import csv
import re
import os
from pathlib import Path

# Project paths
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"


def extract_raw_from_answers_file(answers_path: str) -> str:
    """Extract KenPom data from the Claude answers file."""
    with open(answers_path, "r", encoding="utf-8", newline='') as f:
        content = f.read()

    # The KenPom data is the value of the first question, between =" and ", "What tech stack
    start_marker = '="'
    start_idx = content.index(start_marker) + len(start_marker)

    end_marker = '", "What tech stack'
    end_idx = content.index(end_marker)

    return content[start_idx:end_idx]


def parse_kenpom_raw(raw_text: str) -> list[dict]:
    """
    Parse raw KenPom data from a continuous string.

    The raw data uses \\r (carriage return) as the record separator between teams,
    and \\t (tab) as the field separator within each team entry. Header rows
    containing "Strength of Schedule" appear periodically and are skipped.

    Args:
        raw_text: The raw KenPom data as a continuous string.

    Returns:
        List of dicts with keys: Rank, Team, Seed, Conference, Record, W, L,
        NetRtg, ORtg, ORtg_Rank, DRtg, DRtg_Rank, AdjT, AdjT_Rank
    """
    # The raw data uses \r (carriage return) as record separators.
    # If \r characters are present, split on them. Otherwise, if \r was stripped
    # (e.g., by reading in text mode on Windows), fall back to regex splitting.
    if '\r' in raw_text:
        records = raw_text.split('\r')
    else:
        # Fallback: split where a digit is followed by a number+tab+uppercase letter
        # (i.e., NCSOS_rank of previous team followed by rank of next team)
        split_text = re.sub(r'(\d)(\d{1,3})\t([A-Z])', r'\1\n\2\t\3', raw_text)
        records = split_text.split('\n')

    teams = []
    for record in records:
        record = record.strip()
        if not record:
            continue

        # Skip header rows (contain "Strength of Schedule", "Rk", "Team", etc.)
        if 'Strength of Schedule' in record or 'NCSOS' in record:
            continue
        if record.startswith('Rk') or record.startswith('Team'):
            continue

        fields = record.split('\t')

        # Filter out junk entries
        if len(fields) < 10:
            continue

        # First field should be the rank (a number)
        try:
            rank = int(fields[0])
        except ValueError:
            continue

        if rank < 1 or rank > 365:
            continue

        # Second field is team name, possibly with seed
        team_seed = fields[1].strip()

        # Extract seed: a 1-2 digit number at the end of the team name
        seed_match = re.match(r'^(.+?)\s+(\d{1,2})$', team_seed)
        if seed_match:
            team_name = seed_match.group(1).strip()
            seed = int(seed_match.group(2))
            # Sanity check: seeds are 1-16 in tournament
            if seed < 1 or seed > 16:
                # Not a real seed, it's part of the team name
                team_name = team_seed
                seed = None
        else:
            team_name = team_seed
            seed = None

        # Parse remaining fields
        try:
            conference = fields[2].strip()
            record_str = fields[3].strip()
            w, l = record_str.split('-')
            net_rtg = float(fields[4].replace('+', ''))
            o_rtg = float(fields[5])
            o_rtg_rank = int(fields[6])
            d_rtg = float(fields[7])
            d_rtg_rank = int(fields[8])
            adj_t = float(fields[9])
            adj_t_rank = int(fields[10])
        except (ValueError, IndexError) as e:
            print(f"Warning: Could not parse team at rank {rank}: {e}")
            print(f"  Fields: {fields[:12]}")
            continue

        teams.append({
            'Rank': rank,
            'Team': team_name,
            'Seed': seed,
            'Conference': conference,
            'Record': record_str,
            'W': int(w),
            'L': int(l),
            'NetRtg': net_rtg,
            'ORtg': o_rtg,
            'ORtg_Rank': o_rtg_rank,
            'DRtg': d_rtg,
            'DRtg_Rank': d_rtg_rank,
            'AdjT': adj_t,
            'AdjT_Rank': adj_t_rank,
        })

    return teams


def parse_kenpom_csv(csv_path: str) -> list[dict]:
    """Parse a cleaned KenPom CSV file (e.g., kenpom.csv)."""
    teams = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seed = row.get('Seed', '')
            teams.append({
                'Rank': int(row['Rank']),
                'Team': row['Team'],
                'Seed': int(seed) if seed and seed.strip() else None,
                'Conference': row['Conference'],
                'Record': row['Record'],
                'W': int(row['W']),
                'L': int(row['L']),
                'NetRtg': float(row['NetRtg']),
                'ORtg': float(row['ORtg']),
                'ORtg_Rank': int(row['ORtg_Rank']),
                'DRtg': float(row['DRtg']),
                'DRtg_Rank': int(row['DRtg_Rank']),
                'AdjT': float(row['AdjT']),
                'AdjT_Rank': int(row['AdjT_Rank']),
            })
    return teams


def save_teams_csv(teams: list[dict], output_path: str) -> None:
    """Save parsed team data to CSV."""
    fieldnames = [
        'Rank', 'Team', 'Seed', 'Conference', 'Record', 'W', 'L',
        'NetRtg', 'ORtg', 'ORtg_Rank', 'DRtg', 'DRtg_Rank', 'AdjT', 'AdjT_Rank'
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for team in teams:
            row = dict(team)
            if row['Seed'] is None:
                row['Seed'] = ''
            writer.writerow(row)


def main():
    """Main entry point: parse raw KenPom data and save to CSV files."""
    raw_path = DATA_DIR / "kenpom_raw.txt"
    all_csv_path = DATA_DIR / "kenpom.csv"
    tourney_csv_path = DATA_DIR / "kenpom_tournament.csv"

    # Try to load from raw text file
    if raw_path.exists():
        print(f"Reading raw data from {raw_path}")
        # Use newline='' to preserve \r characters (they are record separators)
        with open(raw_path, 'r', encoding='utf-8', newline='') as f:
            raw_text = f.read()
    else:
        # Try the answers file
        answers_path = (
            Path.home() / ".claude" / "projects"
            / "C--Users-junk7-KroolWorld-BasketballProjections"
            / "e3d2db19-accb-4835-9372-c0a6ee4cb9ae"
            / "tool-results"
            / "toolu_018HYk2MgXrihr7Lhmwubrrn.txt"
        )
        if answers_path.exists():
            print(f"Extracting raw data from answers file: {answers_path}")
            raw_text = extract_raw_from_answers_file(str(answers_path))
            # Save it for future use
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(raw_path, 'w', encoding='utf-8', newline='') as f:
                f.write(raw_text)
            print(f"Saved raw data to {raw_path}")
        else:
            print("Error: No raw data file found.")
            print(f"  Expected: {raw_path}")
            print(f"  Or: {answers_path}")
            return

    # Parse the raw data
    teams = parse_kenpom_raw(raw_text)
    # Deduplicate by (Rank, Team) — raw paste often contains the table twice
    seen = set()
    unique_teams = []
    for t in teams:
        key = (t['Rank'], t['Team'])
        if key not in seen:
            seen.add(key)
            unique_teams.append(t)
    if len(unique_teams) < len(teams):
        print(f"Removed {len(teams) - len(unique_teams)} duplicate entries")
    teams = unique_teams
    print(f"Parsed {len(teams)} teams")

    # Save all teams
    save_teams_csv(teams, str(all_csv_path))
    print(f"Saved all teams to {all_csv_path}")

    # Save tournament teams only
    tourney_teams = [t for t in teams if t['Seed'] is not None]
    save_teams_csv(tourney_teams, str(tourney_csv_path))
    print(f"Saved {len(tourney_teams)} tournament teams to {tourney_csv_path}")

    # Print summary
    print("\n--- Summary ---")
    print(f"Total teams: {len(teams)}")
    print(f"Tournament teams: {len(tourney_teams)}")
    if tourney_teams:
        print("\nTournament teams by seed:")
        for seed_num in range(1, 17):
            seed_teams = [t for t in tourney_teams if t['Seed'] == seed_num]
            if seed_teams:
                names = ', '.join(t['Team'] for t in seed_teams)
                print(f"  {seed_num}: {names}")


if __name__ == "__main__":
    main()
