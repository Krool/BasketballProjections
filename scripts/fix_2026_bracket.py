"""One-shot fix for 2026 bracket data.

The original ingested data had `alive=1` on UConn players (and players_left
counts matching UConn ownership), but Michigan actually won the championship
69-63. This script:

  1. Rebuilds bracket_outcome.json with Michigan as champion and a full
     games[] list (63 games) with winner/loser/scores derived from the
     actual NCAA results.
  2. Flips the `alive` column in player_results.csv.
  3. Marks Tyler Bilodeau (UCLA) as in_tournament_injury (confirmed).
  4. Recomputes players_left in entry_totals.csv from the new alive flags.
"""
import csv
import json
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "archive" / "2026" / "actual"

# ----- Game data from official 2026 NCAA tournament results -----
# Each tuple: (round, region, winner, winner_seed, loser, loser_seed, w_score, l_score)
# Region "Final" used for F4 / championship games

GAMES = [
    # ============ ROUND OF 64 ============
    # Midwest (Michigan's region)
    ("r64","Midwest","Michigan",1,"Howard",16,101,80),
    ("r64","Midwest","Saint Louis",9,"Georgia",8,102,77),
    ("r64","Midwest","Texas Tech",5,"Akron",12,91,71),
    ("r64","Midwest","Alabama",4,"Hofstra",13,90,70),
    ("r64","Midwest","Tennessee",6,"Miami OH",11,78,56),
    ("r64","Midwest","Virginia",3,"Wright St.",14,82,73),
    ("r64","Midwest","Kentucky",7,"Santa Clara",10,89,84),
    ("r64","Midwest","Iowa St.",2,"Tennessee St.",15,108,74),
    # East (Duke's region)
    ("r64","East","Duke",1,"Siena",16,71,65),
    ("r64","East","TCU",9,"Ohio St.",8,66,64),
    ("r64","East","St. John's",5,"Northern Iowa",12,79,53),
    ("r64","East","Kansas",4,"Cal Baptist",13,68,60),
    ("r64","East","Louisville",6,"South Florida",11,83,79),
    ("r64","East","Michigan St.",3,"North Dakota St.",14,92,67),
    ("r64","East","UCLA",7,"UCF",10,75,71),
    ("r64","East","Connecticut",2,"Furman",15,82,71),
    # West (Arizona's region)
    ("r64","West","Arizona",1,"LIU",16,92,52),
    ("r64","West","Utah St.",9,"Villanova",8,86,76),
    ("r64","West","High Point",12,"Wisconsin",5,83,82),
    ("r64","West","Arkansas",4,"Hawaii",13,97,78),
    ("r64","West","Texas",11,"BYU",6,79,71),
    ("r64","West","Gonzaga",3,"Kennesaw St.",14,73,64),
    ("r64","West","Miami FL",7,"Missouri",10,80,66),
    ("r64","West","Purdue",2,"Queens",15,104,71),
    # South (Florida's region)
    ("r64","South","Florida",1,"Prairie View A&M",16,114,55),
    ("r64","South","Iowa",9,"Clemson",8,67,61),
    ("r64","South","Vanderbilt",5,"McNeese",12,78,68),
    ("r64","South","Nebraska",4,"Troy",13,76,47),
    ("r64","South","VCU",11,"North Carolina",6,82,78),
    ("r64","South","Illinois",3,"Penn",14,105,70),
    ("r64","South","Texas A&M",10,"Saint Mary's",7,63,50),
    ("r64","South","Houston",2,"Idaho",15,78,47),
    # ============ ROUND OF 32 ============
    # Midwest
    ("r32","Midwest","Michigan",1,"Saint Louis",9,95,72),
    ("r32","Midwest","Alabama",4,"Texas Tech",5,90,65),
    ("r32","Midwest","Tennessee",6,"Virginia",3,79,72),
    ("r32","Midwest","Iowa St.",2,"Kentucky",7,82,63),
    # East
    ("r32","East","Duke",1,"TCU",9,81,58),
    ("r32","East","St. John's",5,"Kansas",4,67,65),
    ("r32","East","Michigan St.",3,"Louisville",6,77,69),
    ("r32","East","Connecticut",2,"UCLA",7,73,57),
    # West
    ("r32","West","Arizona",1,"Utah St.",9,78,66),
    ("r32","West","Arkansas",4,"High Point",12,94,88),
    ("r32","West","Texas",11,"Gonzaga",3,74,68),
    ("r32","West","Purdue",2,"Miami FL",7,79,69),
    # South
    ("r32","South","Iowa",9,"Florida",1,73,72),
    ("r32","South","Nebraska",4,"Vanderbilt",5,74,72),
    ("r32","South","Illinois",3,"VCU",11,76,55),
    ("r32","South","Houston",2,"Texas A&M",10,88,57),
    # ============ SWEET 16 ============
    ("s16","Midwest","Michigan",1,"Alabama",4,90,77),
    ("s16","Midwest","Tennessee",6,"Iowa St.",2,76,62),
    ("s16","East","Duke",1,"St. John's",5,80,75),
    ("s16","East","Connecticut",2,"Michigan St.",3,67,63),
    ("s16","West","Arizona",1,"Arkansas",4,109,88),
    ("s16","West","Purdue",2,"Texas",11,79,77),
    ("s16","South","Iowa",9,"Nebraska",4,77,71),
    ("s16","South","Illinois",3,"Houston",2,65,55),
    # ============ ELITE 8 ============
    ("e8","Midwest","Michigan",1,"Tennessee",6,95,62),
    ("e8","East","Connecticut",2,"Duke",1,73,72),
    ("e8","West","Arizona",1,"Purdue",2,79,64),
    ("e8","South","Illinois",3,"Iowa",9,71,59),
    # ============ FINAL FOUR ============
    ("f4","Midwest/West","Michigan",1,"Arizona",1,91,73),
    ("f4","East/South","Connecticut",2,"Illinois",3,71,62),
    # ============ CHAMPIONSHIP ============
    ("championship","Final","Michigan",1,"Connecticut",2,69,63),
]

def main():
    # ----- Build bracket_outcome.json -----
    games_out = []
    advanced = defaultdict(set)  # round -> set of advancing teams
    for r, region, w, ws, l, ls, wsc, lsc in GAMES:
        games_out.append({
            "round": r, "region": region,
            "winner": w, "winner_seed": ws, "winner_score": wsc,
            "loser": l, "loser_seed": ls, "loser_score": lsc,
        })

    # Derive round membership from games
    teams_by_round = {
        "round_of_32": set(),  # teams that won R64 (i.e., played in R32)
        "sweet_sixteen": set(),
        "elite_eight": set(),
        "final_four": set(),
        "finalists": set(),
        "champion": None,
    }
    for g in games_out:
        if g["round"] == "r64":
            teams_by_round["round_of_32"].add(g["winner"])
        elif g["round"] == "r32":
            teams_by_round["sweet_sixteen"].add(g["winner"])
        elif g["round"] == "s16":
            teams_by_round["elite_eight"].add(g["winner"])
        elif g["round"] == "e8":
            teams_by_round["final_four"].add(g["winner"])
        elif g["round"] == "f4":
            teams_by_round["finalists"].add(g["winner"])
        elif g["round"] == "championship":
            teams_by_round["champion"] = g["winner"]
            # Both teams in the championship game are finalists
            teams_by_round["finalists"].add(g["winner"])
            teams_by_round["finalists"].add(g["loser"])

    bracket = {
        "year": 2026,
        "champion": teams_by_round["champion"],
        "finalists": sorted(teams_by_round["finalists"]),
        "final_four": sorted(teams_by_round["final_four"]),
        "elite_eight": sorted(teams_by_round["elite_eight"]),
        "sweet_sixteen": sorted(teams_by_round["sweet_sixteen"]),
        "round_of_32": sorted(teams_by_round["round_of_32"]),
        "games": games_out,
        "note": "games[] includes actual scores from official 2026 NCAA tournament results.",
    }
    json.dump(bracket, open(A / "bracket_outcome.json", "w"), indent=2)
    print(f"Wrote bracket_outcome.json: {len(games_out)} games, champion = {bracket['champion']}")

    # ----- Update player_results.csv: flip alive flags + flag Bilodeau injured -----
    players = list(csv.DictReader(open(A / "player_results.csv")))
    fields = list(players[0].keys())
    champ_team = bracket["champion"]
    flipped = 0
    for p in players:
        new_alive = "1" if p["team"] == champ_team else "0"
        if p["alive"] != new_alive:
            flipped += 1
        p["alive"] = new_alive
        if p["player"] == "Tyler Bilodeau" and p["team"] == "UCLA":
            p["in_tournament_injury"] = "Injured during tournament; played 0 minutes (confirmed)"
    with open(A / "player_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(players)
    print(f"player_results.csv: flipped {flipped} alive flags; flagged Tyler Bilodeau as injured")

    # ----- Recompute players_left in entry_totals.csv from new alive flags -----
    alive_count = Counter(p["entry"] for p in players if p["alive"] == "1")
    totals = list(csv.DictReader(open(A / "entry_totals.csv")))
    fields_t = list(totals[0].keys())
    for t in totals:
        t["players_left"] = str(alive_count.get(t["entry"], 0))
    with open(A / "entry_totals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields_t)
        w.writeheader(); w.writerows(totals)
    print(f"entry_totals.csv: recomputed players_left ({sum(alive_count.values())} total surviving players)")
    for entry, n in sorted(alive_count.items()):
        print(f"  {entry}: {n}")


if __name__ == "__main__":
    main()
