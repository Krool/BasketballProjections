"""
Scrape per-game player stats for tournament teams from ESPN.

Usage:
    python src/scrape_players_espn.py

Fetches each team's stats page and parses the per-game table for GP, MIN, PTS,
REB, AST per player. Results are cached as JSON files in data/player_stats/ to
avoid redundant requests. The combined output is saved to data/all_player_stats.csv.

ESPN team IDs are hardcoded for all 64 bracket teams. If the bracket changes,
update ESPN_TEAM_IDS accordingly.
"""
import os
import json
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'player_stats')

# ESPN team IDs for all 64 tournament teams
# URL pattern: https://www.espn.com/mens-college-basketball/team/stats/_/id/{ID}
ESPN_TEAM_IDS = {
    # 1-seeds
    "Duke": 150,
    "Arizona": 12,
    "Michigan": 130,
    "Florida": 57,
    # 2-seeds
    "Houston": 248,
    "Iowa St.": 66,
    "Purdue": 2509,
    "Connecticut": 41,
    # 3-seeds
    "Illinois": 356,
    "Michigan St.": 127,
    "Gonzaga": 2250,
    "Virginia": 258,
    # 4-seeds
    "Nebraska": 158,
    "Arkansas": 8,
    "Alabama": 333,
    "Kansas": 2305,
    # 5-seeds
    "Vanderbilt": 238,
    "St. John's": 2599,
    "Texas Tech": 2641,
    "Wisconsin": 275,
    # 6-seeds
    "Tennessee": 2633,
    "Louisville": 97,
    "BYU": 252,
    "North Carolina": 153,
    # 7-seeds
    "Saint Mary's": 2608,
    "UCLA": 26,
    "Kentucky": 96,
    "Miami FL": 2390,
    # 8-seeds
    "Ohio St.": 194,
    "Georgia": 61,
    "Villanova": 222,
    "Clemson": 228,
    # 9-seeds
    "Iowa": 2294,
    "Utah St.": 328,
    "Saint Louis": 139,
    "TCU": 2628,
    # 10-seeds
    "Santa Clara": 2541,
    "Texas A&M": 245,
    "Missouri": 142,
    "UCF": 2116,
    # 11-seeds
    "N.C. State": 152,
    "SMU": 2567,
    "VCU": 2670,
    "South Florida": 58,
    # 12-seeds
    "Akron": 2006,
    "McNeese": 2377,
    "Northern Iowa": 2460,
    "High Point": 2272,
    # 13-seeds
    "Hofstra": 2275,
    "Cal Baptist": 2856,
    "Hawaii": 62,
    "Troy": 2653,
    # 14-seeds
    "North Dakota St.": 2449,
    "Wright St.": 2750,
    "Penn": 219,
    "Kennesaw St.": 2320,
    # 15-seeds
    "Idaho": 70,
    "Queens": 2511,
    "Tennessee St.": 2634,
    "Furman": 231,
    # 16-seeds
    "UMBC": 2378,
    "Siena": 2561,
    "LIU": 2344,  # Long Island University
    "Lehigh": 2329,
    # First Four play-in teams (not in bracket.json until winners resolved)
    "Howard": 47,
    "Prairie View A&M": 2504,
    "Texas": 251,
    "Miami OH": 193,
}


def scrape_team_espn(team_name, use_cache=True):
    """
    Scrape player stats for a team from ESPN.
    Returns a list of dicts with player info.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{team_name.replace(' ', '_').replace('.', '')}.json")

    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            if data:  # Only use cache if it has actual data
                return data
        except (json.JSONDecodeError, IOError):
            pass  # Corrupted cache, re-scrape

    if team_name not in ESPN_TEAM_IDS:
        print(f"  WARNING: No ESPN ID for {team_name}")
        return []

    team_id = ESPN_TEAM_IDS[team_name]
    url = f"https://www.espn.com/mens-college-basketball/team/stats/_/id/{team_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 2:
                print(f"  WARNING: Failed to fetch {team_name} (ESPN ID {team_id}): {e}")
                return []
            time.sleep(10)
    else:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    players = []

    # ESPN renders stats in table rows. Look for the stats tables.
    # The page typically has multiple stat tables; we want per-game stats.
    tables = soup.find_all('table')

    if not tables:
        print(f"  WARNING: No tables found for {team_name}")
        return []

    # ESPN page has 4 tables:
    #   Table 0: Player names (per-game section)
    #   Table 1: Per-game stats - columns: GP, MIN, PTS, REB, AST, STL, BLK, TO, FG%, FT%, 3P%
    #   Table 2: Player names (totals section)
    #   Table 3: Season totals
    # We want Table 0 (names) + Table 1 (per-game stats)

    name_tables = []
    stat_tables = []

    for table in tables:
        thead = table.find('thead')
        tbody = table.find('tbody')
        if not tbody:
            continue

        rows = tbody.find_all('tr')
        if not rows:
            continue

        # Get headers to identify table type
        hdrs = []
        if thead:
            hdrs = [th.text.strip().upper() for th in thead.find_all(['th', 'td'])]

        if hdrs == ['NAME'] or (len(hdrs) == 1 and 'NAME' in hdrs[0].upper()):
            # Name table
            names = []
            for row in rows:
                link = row.find('a')
                if link:
                    names.append(link.text.strip())
                else:
                    td = row.find('td')
                    if td:
                        names.append(td.text.strip())
            name_tables.append(names)
        elif 'GP' in hdrs and 'PTS' in hdrs:
            # Stats table with headers - parse by column name
            col_map = {h: i for i, h in enumerate(hdrs)}
            parsed = []
            for row in rows:
                cells = [td.text.strip() for td in row.find_all('td')]
                parsed.append((cells, col_map))
            stat_tables.append((parsed, col_map))

    # Match first name table with first stat table (per-game)
    if name_tables and stat_tables:
        names = name_tables[0]
        stat_rows, col_map = stat_tables[0]

        gp_idx = col_map.get('GP', 0)
        min_idx = col_map.get('MIN', 1)
        pts_idx = col_map.get('PTS', 2)
        reb_idx = col_map.get('REB')
        ast_idx = col_map.get('AST')

        for i, name in enumerate(names):
            if i >= len(stat_rows):
                break
            cells, _ = stat_rows[i]
            try:
                gp = int(cells[gp_idx])
                mpg = float(cells[min_idx])
                ppg = float(cells[pts_idx])
                rpg = float(cells[reb_idx]) if reb_idx is not None and reb_idx < len(cells) else 0.0
                apg = float(cells[ast_idx]) if ast_idx is not None and ast_idx < len(cells) else 0.0

                if gp > 0:
                    players.append({
                        'player': name,
                        'team': team_name,
                        'games_played': gp,
                        'mpg': round(mpg, 1),
                        'ppg': round(ppg, 1),
                        'rpg': round(rpg, 1),
                        'apg': round(apg, 1),
                    })
            except (ValueError, IndexError):
                continue

    # Cache results
    with open(cache_file, 'w') as f:
        json.dump(players, f, indent=2)

    return players


def scrape_all_tournament_teams(tournament_teams, use_cache=True, delay=3.0):
    """
    Scrape player stats for all tournament teams from ESPN.
    """
    all_players = []

    for i, team in enumerate(tournament_teams):
        print(f"[{i+1}/{len(tournament_teams)}] Scraping {team}...", end=" ", flush=True)

        # Check if we'll hit the network (cache miss)
        cache_file = os.path.join(CACHE_DIR, f"{team.replace(' ', '_').replace('.', '')}.json")
        will_fetch = not use_cache or not os.path.exists(cache_file)

        players = scrape_team_espn(team, use_cache=use_cache)
        all_players.extend(players)

        if players:
            top = max(players, key=lambda p: p['ppg'])
            print(f"{len(players)} players, top: {top['player']} ({top['ppg']} PPG)")
        else:
            print("NO DATA")

        # Rate limit when we actually hit the network
        if will_fetch:
            time.sleep(delay)

    df = pd.DataFrame(all_players)
    if not df.empty:
        output_path = os.path.join(DATA_DIR, 'all_player_stats.csv')
        df.to_csv(output_path, index=False)
        print(f"\nSaved {len(df)} players to {output_path}")

    return df


if __name__ == '__main__':
    with open(os.path.join(DATA_DIR, 'bracket.json')) as f:
        bracket = json.load(f)

    bracket_teams = set()
    for region, seeds in bracket['regions'].items():
        for seed, team in seeds.items():
            if team:
                bracket_teams.add(team)

    df = scrape_all_tournament_teams(sorted(bracket_teams), use_cache=True, delay=3.0)
    print(f"\nTotal players scraped: {len(df)}")
    if not df.empty:
        print(f"\nTop 20 scorers:")
        print(df.nlargest(20, 'ppg')[['player', 'team', 'ppg', 'mpg', 'games_played']].to_string(index=False))
