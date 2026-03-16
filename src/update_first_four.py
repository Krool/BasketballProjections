"""
Update bracket.json with First Four play-in results.

Run this after the First Four games (March 17-18) and before the draft.
Then re-run main.py to regenerate projections.

First Four matchups (2026):
  West 11-seed:    N.C. State vs Texas       → winner plays BYU
  Midwest 16-seed: UMBC vs Howard            → winner plays Michigan
  Midwest 11-seed: SMU vs Miami (OH)         → winner plays Tennessee
  South 16-seed:   Lehigh vs Prairie View A&M → winner plays Florida

Usage:
    python src/update_first_four.py

Then follow prompts to enter winners, or pass them as arguments:
    python src/update_first_four.py --west11 "Texas" --mw16 "Howard" --mw11 "SMU" --south16 "Lehigh"
"""
import os
import sys
import json
import argparse

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BRACKET_PATH = os.path.join(DATA_DIR, 'bracket.json')

# First Four slots: (region, seed, current_team, opponent_not_in_bracket)
FIRST_FOUR = [
    {
        'region': 'West',
        'seed': '11',
        'current': 'N.C. State',
        'opponent': 'Texas',
        'label': 'West 11-seed: N.C. State vs Texas',
    },
    {
        'region': 'Midwest',
        'seed': '16',
        'current': 'UMBC',
        'opponent': 'Howard',
        'label': 'Midwest 16-seed: UMBC vs Howard',
    },
    {
        'region': 'Midwest',
        'seed': '11',
        'current': 'SMU',
        'opponent': 'Miami (OH)',
        'label': 'Midwest 11-seed: SMU vs Miami (OH)',
    },
    {
        'region': 'South',
        'seed': '16',
        'current': 'Lehigh',
        'opponent': 'Prairie View A&M',
        'label': 'South 16-seed: Lehigh vs Prairie View A&M',
    },
]


def main():
    parser = argparse.ArgumentParser(description='Update bracket with First Four results')
    parser.add_argument('--west11', help='Winner of N.C. State vs Texas')
    parser.add_argument('--mw16', help='Winner of UMBC vs Howard')
    parser.add_argument('--mw11', help='Winner of SMU vs Miami (OH)')
    parser.add_argument('--south16', help='Winner of Lehigh vs Prairie View A&M')
    args = parser.parse_args()

    arg_map = {
        'West-11': args.west11,
        'Midwest-16': args.mw16,
        'Midwest-11': args.mw11,
        'South-16': args.south16,
    }

    with open(BRACKET_PATH) as f:
        bracket = json.load(f)

    changes = []

    for slot in FIRST_FOUR:
        key = f"{slot['region']}-{slot['seed']}"
        valid = [slot['current'], slot['opponent']]

        winner = arg_map.get(key)
        if not winner:
            print(f"\n{slot['label']}")
            print(f"  Current in bracket: {slot['current']}")
            winner = input(f"  Winner (enter name, or press Enter to keep {slot['current']}): ").strip()
            if not winner:
                winner = slot['current']

        if winner not in valid:
            # Allow partial/case-insensitive matching
            matched = [v for v in valid if v.lower().startswith(winner.lower())]
            if len(matched) == 1:
                winner = matched[0]
            else:
                print(f"  WARNING: '{winner}' not recognized. Expected one of: {valid}")
                continue

        old = bracket['regions'][slot['region']][slot['seed']]
        if old != winner:
            bracket['regions'][slot['region']][slot['seed']] = winner
            changes.append(f"  {slot['region']} {slot['seed']}-seed: {old} → {winner}")
        else:
            changes.append(f"  {slot['region']} {slot['seed']}-seed: {old} (no change)")

    with open(BRACKET_PATH, 'w') as f:
        json.dump(bracket, f, indent=2)

    print(f"\nUpdated {BRACKET_PATH}:")
    for c in changes:
        print(c)

    print("\nNext steps:")
    print("  1. If a new team entered (e.g. Texas replacing N.C. State),")
    print("     add their KenPom data to data/kenpom_tournament.csv")
    print("     and scrape their player stats (delete data/player_stats/<team> cache)")
    print("  2. Re-run: python src/main.py")


if __name__ == '__main__':
    main()
