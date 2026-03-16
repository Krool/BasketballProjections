"""
Scrape player stats (PPG, MPG, GP) for tournament teams from sports-reference.com/cbb.
"""
import os
import json
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'player_stats')
YEAR = 2026

# Mapping from KenPom team names to sports-reference URL slugs
# This needs to be comprehensive for all 64 tournament teams
TEAM_SLUG_MAP = {
    "Duke": "duke",
    "Arizona": "arizona",
    "Michigan": "michigan",
    "Florida": "florida",
    "Houston": "houston",
    "Iowa St.": "iowa-state",
    "Purdue": "purdue",
    "Connecticut": "connecticut",
    "Illinois": "illinois",
    "Michigan St.": "michigan-state",
    "Gonzaga": "gonzaga",
    "Virginia": "virginia",
    "Vanderbilt": "vanderbilt",
    "St. John's": "st-johns-ny",
    "Texas Tech": "texas-tech",
    "Wisconsin": "wisconsin",
    "Tennessee": "tennessee",
    "Louisville": "louisville",
    "BYU": "brigham-young",
    "North Carolina": "north-carolina",
    "Nebraska": "nebraska",
    "Arkansas": "arkansas",
    "Kansas": "kansas",
    "Alabama": "alabama",
    "Saint Mary's": "saint-marys-ca",
    "UCLA": "ucla",
    "Kentucky": "kentucky",
    "Miami FL": "miami-fl",
    "Georgia": "georgia",
    "Villanova": "villanova",
    "Clemson": "clemson",
    "Ohio St.": "ohio-state",
    "Iowa": "iowa",
    "Utah St.": "utah-state",
    "Saint Louis": "saint-louis",
    "TCU": "texas-christian",
    "Santa Clara": "santa-clara",
    "Texas A&M": "texas-am",
    "N.C. State": "north-carolina-state",
    "SMU": "southern-methodist",
    "VCU": "virginia-commonwealth",
    "Texas": "texas",
    "Marquette": "marquette",
    "Oregon": "oregon",
    "Missouri": "missouri",
    "Mississippi St.": "mississippi-state",
    "Drake": "drake",
    "Colorado St.": "colorado-state",
    "Boise St.": "boise-state",
    "Grand Canyon": "grand-canyon",
    "McNeese": "mcneese-state",
    "High Point": "high-point",
    "Lipscomb": "lipscomb",
    "Troy": "troy",
    "Akron": "akron",
    "Wofford": "wofford",
    "Robert Morris": "robert-morris",
    "Norfolk St.": "norfolk-state",
    "SIU Edwardsville": "southern-illinois-edwardsville",
    "Montana St.": "montana-state",
    "American": "american",
    "Omaha": "nebraska-omaha",
    "Cal Baptist": "california-baptist",
    "Kennesaw St.": "kennesaw-state",
    "LIU": "long-island-university",
    "Wright St.": "wright-state",
    "North Dakota St.": "north-dakota-state",
    "Northern Iowa": "northern-iowa",
    "Tennessee St.": "tennessee-state",
    "South Florida": "south-florida",
    "UCF": "central-florida",
    "N.C. State": "north-carolina-state",
    "Queens": "queens-nc",
}


def get_team_slug(team_name):
    """Get sports-reference URL slug for a team."""
    if team_name in TEAM_SLUG_MAP:
        return TEAM_SLUG_MAP[team_name]
    # Fallback: lowercase, replace spaces/periods with hyphens
    slug = team_name.lower().replace('.', '').replace("'", '').replace(' ', '-')
    return slug


def scrape_team_roster(team_name, use_cache=True):
    """
    Scrape player stats for a team from sports-reference.
    Returns a list of dicts with player info.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{team_name.replace(' ', '_').replace('.', '')}.json")

    if use_cache and os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)

    slug = get_team_slug(team_name)
    url = f"https://www.sports-reference.com/cbb/schools/{slug}/men/{YEAR}.html"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # Retry with exponential backoff for rate limiting
    for attempt in range(4):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait = 10 * (2 ** attempt)  # 10s, 20s, 40s, 80s
                print(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/4)...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 3:
                print(f"  WARNING: Failed to fetch {team_name} ({url}): {e}")
                return []
            wait = 10 * (2 ** attempt)
            print(f"  Request failed, retrying in {wait}s...")
            time.sleep(wait)
    else:
        print(f"  WARNING: Exhausted retries for {team_name}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Find the per-game stats table
    table = soup.find('table', id='players_per_game')
    if not table:
        table = soup.find('table', id='per_game')
    if not table:
        print(f"  WARNING: No stats table found for {team_name}")
        return []

    players = []
    tbody = table.find('tbody')
    if not tbody:
        return []

    for row in tbody.find_all('tr'):
        # Skip header rows within tbody
        if row.get('class') and 'thead' in row.get('class', []):
            continue

        cells = row.find_all(['th', 'td'])
        if len(cells) < 5:
            continue

        # Extract player name (sports-reference uses 'name_display' or 'player')
        player_cell = (row.find('td', {'data-stat': 'name_display'})
                       or row.find('th', {'data-stat': 'name_display'})
                       or row.find('th', {'data-stat': 'player'})
                       or row.find('td', {'data-stat': 'player'}))
        if not player_cell:
            continue

        player_link = player_cell.find('a')
        player_name = player_link.text.strip() if player_link else player_cell.text.strip()

        if not player_name or player_name == 'Player':
            continue

        # Extract stats by data-stat attribute
        def get_stat(stat_name):
            cell = row.find('td', {'data-stat': stat_name})
            if cell and cell.text.strip():
                try:
                    return float(cell.text.strip())
                except ValueError:
                    return 0.0
            return 0.0

        gp = get_stat('games') or get_stat('g')
        mpg = get_stat('mp_per_g')
        ppg = get_stat('pts_per_g')
        rpg = get_stat('trb_per_g')
        apg = get_stat('ast_per_g')

        if gp > 0:  # Only include players who actually played
            players.append({
                'player': player_name,
                'team': team_name,
                'games_played': int(gp),
                'mpg': round(mpg, 1),
                'ppg': round(ppg, 1),
                'rpg': round(rpg, 1),
                'apg': round(apg, 1),
            })

    # Cache results
    with open(cache_file, 'w') as f:
        json.dump(players, f, indent=2)

    return players


def scrape_all_tournament_teams(tournament_teams, use_cache=True, delay=3.0):
    """
    Scrape player stats for all tournament teams.

    Args:
        tournament_teams: list of team names
        use_cache: whether to use cached data
        delay: seconds between requests (be polite to sports-reference)

    Returns:
        DataFrame with all player stats
    """
    all_players = []

    for i, team in enumerate(tournament_teams):
        print(f"[{i+1}/{len(tournament_teams)}] Scraping {team}...")
        players = scrape_team_roster(team, use_cache=use_cache)
        all_players.extend(players)

        # Rate limiting - only if we actually made a request (not cached)
        cache_file = os.path.join(CACHE_DIR, f"{team.replace(' ', '_').replace('.', '')}.json")
        if not use_cache or not os.path.exists(cache_file):
            time.sleep(delay)

    df = pd.DataFrame(all_players)
    if not df.empty:
        # Save combined stats
        output_path = os.path.join(DATA_DIR, 'all_player_stats.csv')
        df.to_csv(output_path, index=False)
        print(f"\nSaved {len(df)} players to {output_path}")

    return df


if __name__ == '__main__':
    # Load tournament teams from kenpom data
    kenpom_path = os.path.join(DATA_DIR, 'kenpom_tournament.csv')
    if os.path.exists(kenpom_path):
        kenpom_df = pd.read_csv(kenpom_path)
        teams = kenpom_df['Team'].tolist()
    else:
        print("ERROR: Run parse_kenpom.py first to generate kenpom_tournament.csv")
        exit(1)

    df = scrape_all_tournament_teams(teams, use_cache=True, delay=3.0)
    print(f"\nTotal players scraped: {len(df)}")
    if not df.empty:
        print(f"Average PPG across all players: {df['ppg'].mean():.1f}")
        print(f"\nTop 20 scorers:")
        print(df.nlargest(20, 'ppg')[['player', 'team', 'ppg', 'mpg', 'games_played']].to_string(index=False))
