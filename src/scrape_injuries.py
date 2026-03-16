"""
Scrape injury data from ESPN and merge with manual overrides.
"""
import os
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def scrape_espn_injuries():
    """
    Scrape injury reports from ESPN college basketball.
    Returns a list of dicts with player injury info.
    """
    url = "https://www.espn.com/mens-college-basketball/injuries"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"WARNING: Failed to scrape ESPN injuries: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    injuries = []

    # ESPN injury pages typically have team sections with player tables
    # The exact structure may vary; this is a best-effort parse
    team_sections = soup.find_all('div', class_='ResponsiveTable')

    for section in team_sections:
        # Try to find team name
        team_header = section.find_previous('div', class_='injuries__teamHeader')
        team_name = ''
        if team_header:
            team_link = team_header.find('a')
            team_name = team_link.text.strip() if team_link else ''

        # Find player rows
        rows = section.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                player_name = cells[0].text.strip()
                status = cells[1].text.strip()  # e.g., "Out", "Day-To-Day"
                comment = cells[2].text.strip() if len(cells) > 2 else ''

                if player_name and status:
                    injuries.append({
                        'player': player_name,
                        'team': team_name,
                        'status': status.upper(),
                        'notes': comment,
                        'source': 'espn'
                    })

    return injuries


def load_manual_overrides():
    """
    Load manual injury overrides from CSV file.
    Format: player,team,status,notes
    Status values: OUT, RETURNING, DAY-TO-DAY, HEALTHY
    """
    override_path = os.path.join(DATA_DIR, 'injury_overrides.csv')

    if not os.path.exists(override_path):
        # Create template file
        template_df = pd.DataFrame(columns=['player', 'team', 'status', 'notes'])
        template_df.to_csv(override_path, index=False)
        print(f"Created empty injury overrides template at {override_path}")
        return []

    df = pd.read_csv(override_path)
    if df.empty:
        return []

    overrides = []
    for _, row in df.iterrows():
        overrides.append({
            'player': str(row['player']).strip(),
            'team': str(row['team']).strip(),
            'status': str(row['status']).strip().upper(),
            'notes': str(row.get('notes', '')).strip(),
            'source': 'manual'
        })

    return overrides


def get_combined_injuries(tournament_teams=None):
    """
    Combine ESPN scraped injuries with manual overrides.
    Manual overrides take precedence.

    Args:
        tournament_teams: optional list of team names to filter to

    Returns:
        DataFrame with injury data
    """
    print("Scraping ESPN injury reports...")
    espn_injuries = scrape_espn_injuries()
    print(f"  Found {len(espn_injuries)} injuries from ESPN")

    print("Loading manual overrides...")
    manual_overrides = load_manual_overrides()
    print(f"  Found {len(manual_overrides)} manual overrides")

    # Combine: start with ESPN data
    all_injuries = {(inj['player'].lower(), inj['team'].lower()): inj for inj in espn_injuries}

    # Manual overrides take precedence
    for override in manual_overrides:
        key = (override['player'].lower(), override['team'].lower())
        all_injuries[key] = override

    injuries_list = list(all_injuries.values())

    if not injuries_list:
        print("No injuries found.")
        return pd.DataFrame(columns=['player', 'team', 'status', 'notes', 'source'])

    df = pd.DataFrame(injuries_list)

    # Filter to tournament teams if provided
    if tournament_teams:
        team_names_lower = [t.lower() for t in tournament_teams]
        df = df[df['team'].str.lower().isin(team_names_lower)]

    # Save combined injuries
    output_path = os.path.join(DATA_DIR, 'injuries_combined.csv')
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} injury records to {output_path}")

    return df


if __name__ == '__main__':
    df = get_combined_injuries()
    if not df.empty:
        print("\nInjury Report:")
        print(df.to_string(index=False))
    else:
        print("\nNo injuries to report. Add entries to data/injury_overrides.csv if needed.")
