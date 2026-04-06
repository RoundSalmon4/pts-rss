
import requests, json, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

MLS_TEAM_CODES = {
    "toronto-fc": "TOR",
    "colorado-rapids": "COL",
    "real-salt-lake": "RSL",
    "sporting-kansas-city": "SKC",
    "new-england-revolution": "NER",
    "cf-montreal": "MTL",
    "new-york-red-bulls": "RBNY",
    "fc-cincinnati": "CIN",
    "new-york-city-fc": "NYC",
    "st-louis-city-sc": "STL",
    "inter-miami-cf": "MIA",
    "austin-fc": "ATX",
    "dc-united": "DC",
    "fc-dallas": "DAL",
    "charlotte-fc": "CLT",
    "philadelphia-union": "PHI",
    "atlanta-united": "ATL",
    "columbus-crew": "CLB",
    "chicago-fire-fc": "CHI",
    "nashville-sc": "NSH",
    "houston-dynamo-fc": "HOU",
    "seattle-sounders-fc": "SEA",
    "los-angeles-football-club": "LAFC",
    "orlando-city-sc": "ORL",
    "vancouver-whitecaps-fc": "VAN",
    "portland-timbers": "POR",
    "san-jose-earthquakes": "SJE",
    "san-diego-fc": "SD",
    "la-galaxy": "LAG",
    "minnesota-united-fc": "MIN",
    "vancouver-whitecaps": "VAN",
    "sporting-kc": "SKC",
    "real-salt": "RSL",
    "la-galaxy": "LAG",
    "ny-red-bulls": "RBNY",
}

NWSL_TEAM_CODES = {
    "portland-thorns-fc": "POR",
    "north-carolina-courage": "NC",
    "seattle-reign": "SEA",
    "kansas-city-current": "KC",
    "angel-city": "LA",
    "orlando-pride": "ORL",
    "houston-dash": "HOU",
    "wash-nji": "WAS",
    "chicago-red-stars": "CHI",
    "sky-blue": "NJ",
    "utah-royals": "UTA",
    "gotham": "NJ",
    "bay-fc": "BAY",
    "san-diego-wave": "SD",
    "nj-ny-gotham": "NJ",
    "denver-summit": "DEN",
    "portland-thorns": "POR",
}

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "state.json"
RSS_DIR = ROOT / "rss"
TEAM_DIR = RSS_DIR / "teams"

BASE_URL = "https://plaintextsports.com"
TIMEZONE = timezone(timedelta(hours=-5))
KNOWN_LEAGUES = {
    "nba": "nba",
    "mlb": "mlb",
    "nhl": "nhl",
    "nfl": "nfl",
    "wnba": "wnba",
    "ncaa-mb": "ncaamb",
    "ncaa-wb": "ncaawb",
    "champions-league": "champions-league",
    "europa-league": "europa-league",
    "premier-league": "premier-league",
    "world-cup": "world-cup",
    "mls": "mls",
    "nwsl": "nwsl",
}

def discover_leagues():
    html = fetch(BASE_URL + "/")
    leagues = {}
    for sport in KNOWN_LEAGUES:
        pattern = f'href="(/{sport}/[^"]*)"'
        if re.search(pattern, html):
            leagues[KNOWN_LEAGUES[sport]] = BASE_URL + "/" + sport + "/"
        else:
            leagues[KNOWN_LEAGUES[sport]] = BASE_URL + "/" + sport + "/"
    return leagues

HEADERS = {"User-Agent": "plaintextsports-rss/3.0"}

RSS_DIR.mkdir(exist_ok=True)
TEAM_DIR.mkdir(parents=True, exist_ok=True)

def validate_state(state):
    if "published" not in state:
        state["published"] = {}
    
    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    valid_dates = {today, yesterday}
    
    for league, games in list(state.get("published", {}).items()):
        if not isinstance(games, dict):
            state["published"][league] = {}
            continue
        
        keys_to_remove = set()
        for gid, title in games.items():
            match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
            if not match:
                keys_to_remove.add(gid)
                continue
            
            league_key, team1, team2, date = match.groups()
            
            if date not in valid_dates:
                keys_to_remove.add(gid)
                continue
            
            base_key = f"{league_key}-{min(team1, team2)}-{max(team1, team2)}-{date}"
            if base_key != gid:
                keys_to_remove.add(gid)
        
        for key in keys_to_remove:
            del games[key]
    
    return state

def load_state():
    if not STATE_FILE.exists():
        return {"published": {}}
    data = json.loads(STATE_FILE.read_text())
    
    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    valid_dates = {today, yesterday}
    
    for league, items in data.get("published", {}).items():
        if isinstance(items, list):
            new_dict = {}
            for item in items:
                new_dict[item] = ""
            data["published"][league] = new_dict
    
    for league, games in list(data.get("published", {}).items()):
        keys_to_remove = set()
        for gid in games.keys():
            match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
            if match and match.group(4) not in valid_dates:
                keys_to_remove.add(gid)
        for gid in keys_to_remove:
            del games[gid]
    
    seen_gids = {}
    for league, games in list(data.get("published", {}).items()):
        to_remove = set()
        for gid, title in games.items():
            match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
            if match:
                league_key, team1, team2, date = match.groups()
                base_gid = f"{league_key}-{min(team1, team2)}-{max(team1, team2)}-{date}"
                
                if base_gid in seen_gids:
                    existing_gid, existing_title = seen_gids[base_gid]
                    if existing_title == existing_gid and title != gid:
                        to_remove.add(existing_gid)
                        seen_gids[base_gid] = (gid, title)
                    elif title != gid:
                        to_remove.add(gid)
                else:
                    seen_gids[base_gid] = (gid, title)
        
        for gid in to_remove:
            if gid in games:
                del games[gid]
    
    return data

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def fetch(url):
    print(f"Fetching: {url}")
    response = requests.get(url, headers=HEADERS, timeout=20)
    print(f"Status: {response.status_code}, Length: {len(response.text)}")
    return response.text

def extract_games(html, league=None):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    
    use_team_codes = MLS_TEAM_CODES if league in ["mls", "nwsl"] else None
    
    is_ncaa = league in ["ncaamb", "ncaawb"]
    is_uefa = league in ["champions-league", "europa-league", "premier-league"]
    
    team_code_pattern = r"([A-Z]{2,6})\s+(\d+)" if is_ncaa else r"([A-Z]{2,3})\s+(\d+)"
    
    links = soup.find_all("a", href=True)
    print(f"Found {len(links)} total links")
    for game in links:
        href = game.get("href", "")
        
        text = game.get_text()
        
        if "/20" in href:
            if "Final" not in text and "FT" not in text:
                continue
            
            if is_ncaa:
                team_scores = re.findall(r"(\d*\s*[A-Z][A-Z\s]{1,5})\s+(\d+)", text)
            elif is_uefa:
                team_scores = re.findall(r"(\d*\s*[A-Za-z\s]{3,20})\s+(\d+)", text)
            else:
                team_scores = re.findall(team_code_pattern, text)
            
            if len(team_scores) == 2:
                team1 = team_scores[0][0].strip()
                score1 = team_scores[0][1]
                team2 = team_scores[1][0].strip()
                score2 = team_scores[1][1]
                
                if is_ncaa or is_uefa:
                    team1 = re.sub(r"^\d+\s*", "", team1)
                    team2 = re.sub(r"^\d+\s*", "", team2)
                    team1 = team1.replace(" ", "")
                    team2 = team2.replace(" ", "")
                
                ot = "OT" in text or "SO" in text
                games.append(((team1, score1), (team2, score2), ot))
                print(f"    ADDED from link: {team_scores}")
        else:
            if "Final" in text or "FT" in text:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                teams_scores = []
                
                for line in lines:
                    if "Final" in line or "FT" in line:
                        continue
                    parts = line.replace("|", "").split()
                    
                    i = 0
                    while i < len(parts):
                        part = parts[i]
                        
                        seed_with_team = re.match(r"^(\d+)([A-Z]{2,6})$", part)
                        if seed_with_team:
                            team_name = seed_with_team.group(2)
                            i += 1
                            if i < len(parts) and parts[i].isdigit():
                                teams_scores.append((team_name, parts[i]))
                                i += 1
                                continue
                        
                        seed_match = re.match(r"^(\d+)$", part)
                        if seed_match and i + 2 < len(parts):
                            potential_team = parts[i + 1]
                            potential_score = parts[i + 2]
                            team_match = re.match(r"^(\d+)?([A-Z]{2,6})$", potential_team)
                            if team_match and len(team_match.group(2)) >= 2:
                                if potential_score.isdigit():
                                    teams_scores.append((team_match.group(2), potential_score))
                                    i += 3
                                    continue
                        
                        if part.isdigit() and i + 1 < len(parts):
                            next_part = parts[i + 1]
                            if re.match(r"^[A-Z]{2,6}$", next_part):
                                teams_scores.append((next_part, part))
                                i += 2
                                continue
                        
                        match = re.match(r"^(\d+)?([A-Z]{2,6})$", part)
                        if match and len(match.group(2)) >= 2:
                            team_name = match.group(2)
                            if not match.group(1):
                                i += 1
                                if i < len(parts) and parts[i].isdigit():
                                    teams_scores.append((team_name, parts[i]))
                                    i += 1
                                    continue
                        i += 1
                
                if len(teams_scores) >= 2:
                    team1, score1 = teams_scores[0]
                    team2, score2 = teams_scores[1]
                    ot = "OT" in text or "SO" in text
                    games.append(((team1, score1), (team2, score2), ot))
                    print(f"    ADDED from ext-link: {team1} {score1} vs {team2} {score2}")
    
    if not games:
        pre_tags = soup.find_all("pre")
        for pre in pre_tags:
            text = pre.get_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            
            i = 0
            while i < len(lines):
                line = lines[i]
                if "Final" in line or "final" in line or "FT" in line:
                    game_teams = []
                    game_scores = []
                    
                    j = i + 1
                    while j < len(lines) and j < i + 4:
                        next_line = lines[j]
                        if "Final" in next_line or "FT" in next_line:
                            break
                        
                        parts = next_line.replace("|", "").split()
                        for part in parts:
                            if re.match(r"^[A-Z]{2,6}$", part):
                                game_teams.append(part)
                            elif re.match(r"^\d+$", part):
                                game_scores.append(part)
                        
                        if len(game_teams) >= 2 and len(game_scores) >= 2:
                            break
                        j += 1
                    
                    if len(game_teams) >= 2 and len(game_scores) >= 2:
                        ot = "OT" in line or "SO" in line
                        games.append(((game_teams[0], game_scores[0]), (game_teams[1], game_scores[1]), ot))
                        print(f"    ADDED from pre: {game_teams[0]} {game_scores[0]} vs {game_teams[1]} {game_scores[1]}")
                        i = j
                    else:
                        score_match = re.search(r"(\d+)\s*-\s*FT\s*-\s*(\d+)", line)
                        if score_match:
                            a_hrefs = pre.find_all("a", href=True)
                            teams_found = []
                            for a in a_hrefs:
                                team_text = a.get_text(strip=True)
                                if team_text:
                                    parts = team_text.split()
                                    if parts:
                                        last_word = parts[-1]
                                        if len(last_word) >= 2:
                                            teams_found.append(last_word)
                            
                            if len(teams_found) >= 2 and score_match:
                                score1 = score_match.group(1)
                                score2 = score_match.group(2)
                                ot = "OT" in line or "SO" in line
                                games.append(((teams_found[0], score1), (teams_found[1], score2), ot))
                                print(f"    ADDED from pre (FT): {teams_found[0]} {score1} vs {teams_found[1]} {score2}")
                                i += 1
                            else:
                                i += 1
                        else:
                            i += 1
                else:
                    i += 1
    
    if not games:
        game_divs = soup.find_all("div", id=True)
        for div in game_divs:
            div_id = div.get("id", "")
            if div_id in ["page-loaded-wrapper", "full-width-line", "one-line"]:
                continue
            
            text = div.get_text()
            if " - FT - " in text:
                score_match = re.search(r"(\d+)\s*-\s*FT\s*-\s*(\d+)", text)
                if score_match:
                    score1 = score_match.group(1)
                    score2 = score_match.group(2)
                    
                    teams_found = []
                    team_codes = MLS_TEAM_CODES if league == "mls" else (NWSL_TEAM_CODES if league == "nwsl" else {})
                    for a in div.find_all("a", href=True):
                        href = a.get("href", "")
                        if "/teams/" in href:
                            url_part = href.split("/")[-1]
                            team_code = team_codes.get(url_part, url_part.split("-")[0].upper()[:3])
                            if team_code and len(team_code) >= 2:
                                teams_found.append(team_code)
                    
                    if len(teams_found) >= 2:
                        ot = "OT" in text or "SO" in text
                        games.append(((teams_found[0], score1), (teams_found[1], score2), ot))
                        print(f"    ADDED from game div: {teams_found[0]} {score1} vs {teams_found[1]} {score2}")
    
    if not games:
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    cell_texts = [c.get_text(strip=True) for c in cells]
                    full_text = " ".join(cell_texts)
                    
                    if "FT" in full_text or "Final" in full_text.lower():
                        parts = full_text.replace("|", "").split()
                        
                        team1 = None
                        team2 = None
                        score1 = None
                        score2 = None
                        
                        for i, part in enumerate(parts):
                            if " - FT - " in full_text:
                                score_match = re.search(r"(\d+)\s*-\s*FT\s*-\s*(\d+)", full_text)
                                if score_match:
                                    score1 = score_match.group(1)
                                    score2 = score_match.group(2)
                                    
                                    team_part = full_text.split(" - FT - ")[0].strip()
                                    potential_teams = re.findall(r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+([A-Z]{2,5})", team_part)
                                    if len(potential_teams) >= 2:
                                        team1 = potential_teams[0][1]
                                        team2 = potential_teams[1][1]
                                break
                            elif re.match(r"^\d+$", part) and len(part) <= 3:
                                if score1 is None:
                                    score1 = part
                                elif score2 is None:
                                    score2 = part
                            elif len(part) >= 3 and part[0].isupper():
                                if team1 is None:
                                    team1 = part
                                elif team2 is None:
                                    team2 = part
                        
                        if (team1 and team2 and score1 and score2):
                            ot = "OT" in full_text or "SO" in full_text
                            games.append(((team1, score1), (team2, score2), ot))
                            print(f"    ADDED from table: {team1} {score1} vs {team2} {score2}")
    
    print(f"Extracted {len(games)} games")
    return games

def load_existing_items(path):
    if not path.exists():
        return []
    root = ElementTree(file=path).getroot()
    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for item in channel.findall("item"):
        guid = item.find("guid")
        if guid is not None and guid.text and "placeholder" not in guid.text:
            items.append(item)
    return items

def write_feed(path, title, link, description, new_items, state=None):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description

    existing_guids = set()
    for item in load_existing_items(path):
        guid = item.find("guid")
        if guid is not None and guid.text:
            existing_guids.add(guid.text)
            
            for gid, new_title in new_items:
                if gid == guid.text:
                    title_elem = item.find("title")
                    if title_elem is not None and title_elem.text != new_title:
                        title_elem.text = new_title
                    break
            
            channel.append(item)

    for gid, txt in new_items:
        if gid in existing_guids:
            continue
        existing_guids.add(gid)
        it = SubElement(channel, "item")
        SubElement(it, "title").text = txt
        SubElement(it, "link").text = link
        SubElement(it, "guid").text = gid
        SubElement(it, "pubDate").text = datetime.now(TIMEZONE).strftime("%a, %d %b %Y %H:%M:%S %z")

    ElementTree(rss).write(path, encoding="utf-8", xml_declaration=True)

SCORE_CACHE = {}

def write_feed_from_state(path, title, link, description, league, state, leagues=None, new_items_only=False):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description

    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    valid_dates = {today, yesterday}

    if league == "all":
        published = {}
        for league_guids in state.get("published", {}).values():
            for gid, title_text in league_guids.items():
                match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
                if match and match.group(4) in valid_dates:
                    published[gid] = title_text
    else:
        published = {}
        league_games = state.get("published", {}).get(league, {})
        for gid, title_text in league_games.items():
            match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
            if match and match.group(4) in valid_dates:
                published[gid] = title_text

    existing_guids = set()
    if path.exists():
        for item in load_existing_items(path):
            guid = item.find("guid")
            if guid is not None and guid.text:
                existing_guids.add(guid.text)
                channel.append(item)

    league_url = ""
    if league != "all" and leagues:
        league_url = leagues.get(league, "")
    
    for gid, title_text in published.items():
        if gid in existing_guids:
            continue
        if league == "all":
            match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
            if match:
                league_key = match.group(1)
                title_with_league = f"{league_key.upper()}: {title_text}" if title_text and title_text != gid else gid
            else:
                title_with_league = gid
        else:
            if not title_text:
                match = re.match(r"([a-z]+)-([A-Z]+)-([A-Z]+)-(\d{4}-\d{2}-\d{2})", gid)
                if match:
                    league_key, team1, team2, date = match.groups()
                    date_url = f"{league_url}{date}/"
                    if date_url not in SCORE_CACHE:
                        print(f"Fetching for scores: {date_url}")
                        SCORE_CACHE[date_url] = extract_games(fetch(date_url))
                    for away, home, ot in SCORE_CACHE.get(date_url, []):
                        if (away[0] == team1 and home[0] == team2) or (away[0] == team2 and home[0] == team1):
                            suffix = " (OT)" if ot else ""
                            title_text = f"{away[0]} {away[1]} – {home[0]} {home[1]} (Final){suffix}"
                            break
            title_with_league = f"{league.upper()}: {title_text}" if title_text else gid
        
        if not title_with_league or title_with_league == gid:
            title_with_league = gid
        
        existing_guids.add(gid)
        it = SubElement(channel, "item")
        SubElement(it, "title").text = str(title_with_league)
        SubElement(it, "link").text = link
        SubElement(it, "guid").text = gid
        SubElement(it, "pubDate").text = datetime.now(TIMEZONE).strftime("%a, %d %b %Y %H:%M:%S %z")

    placeholder_guid = f"{league}-placeholder"
    if not published:
        it = SubElement(channel, "item")
        SubElement(it, "title").text = "No games available currently"
        SubElement(it, "link").text = link
        SubElement(it, "guid").text = placeholder_guid
        SubElement(it, "pubDate").text = datetime.now(TIMEZONE).strftime("%a, %d %b %Y %H:%M:%S %z")

    ElementTree(rss).write(path, encoding="utf-8", xml_declaration=True)

def main():
    state = load_state()
    state.setdefault("published", {})
    all_new = []

    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Today: {today}, Yesterday: {yesterday}")

    leagues = discover_leagues()
    print(f"Leagues: {leagues}")

    fetch_lock = threading.Lock()
    html_cache = {}
    games_cache = {}

    def fetch_date_combo(args):
        league, url, date_str = args
        if date_str == today:
            check_url = url
        else:
            check_url = f"{url}{date_str}/"
        
        with fetch_lock:
            print(f"Checking {league} {date_str}: {check_url}")
            html = fetch(check_url)
            games = extract_games(html, league)
            print(f"  Games from {date_str}: {games}")
        
        cache_key = (league, date_str)
        with fetch_lock:
            games_cache[cache_key] = games
        return league, date_str, games

    fetch_tasks = []
    for league, url in leagues.items():
        for date_str in [today, yesterday]:
            fetch_tasks.append((league, url, date_str))

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_date_combo, task) for task in fetch_tasks]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error fetching: {e}")

    for league, url in leagues.items():
        state["published"].setdefault(league, {})
        league_new = []

        for date_str in [today, yesterday]:
            games = games_cache.get((league, date_str), [])
            
            for away, home, ot in games:
                away_code = away[0]
                home_code = home[0]
                if away_code > home_code:
                    away_code, home_code = home_code, away_code
                base_gid = f"{league}-{away_code}-{home_code}"
                suffix = " (OT)" if ot else ""
                title = f"{away[0]} {away[1]} – {home[0]} {home[1]} (Final){suffix}"
                
                for check_date in [today, yesterday]:
                    check_gid = f"{base_gid}-{check_date}"
                    if check_gid in state["published"].get(league, {}):
                        existing_title = state["published"][league][check_gid]
                        if existing_title == title:
                            break
                for check_date in [today, yesterday]:
                    check_gid = f"{base_gid}-{check_date}"
                    if check_gid in state["published"].get(league, {}):
                        existing_title = state["published"][league][check_gid]
                        if existing_title == title:
                            break
                else:
                    gid = f"{base_gid}-{date_str}"
                    state["published"][league][gid] = title
                    league_new.append((gid, title))
                    all_new.append((gid, f"{league.upper()}: {title}"))
                    for team in (away[0], home[0]):
                        team_path = TEAM_DIR / f"{league}-{team.lower()}.xml"
                        write_feed(team_path, f"{league.upper()} – {team} Finals", url, f"Final games for {team}", [(gid, title)], state)

        if league_new:
            write_feed(
                RSS_DIR / f"{league}.xml",
                f"Plain Text Sports – {league.upper()} Finals",
                url,
                f"{league.upper()} final scores",
                league_new,
                state
            )
        else:
            write_feed_from_state(
                RSS_DIR / f"{league}.xml",
                f"Plain Text Sports – {league.upper()} Finals",
                url,
                f"{league.upper()} final scores",
                league,
                state,
                leagues,
                new_items_only=True
            )

    if all_new:
        write_feed(
            RSS_DIR / "all-finals.xml",
            "Plain Text Sports – All Finals",
            "https://plaintextsports.com",
            "All leagues final scores",
            all_new,
            state
        )
    else:
        write_feed_from_state(
            RSS_DIR / "all-finals.xml",
            "Plain Text Sports – All Finals",
            "https://plaintextsports.com",
            "All leagues final scores",
            "all",
            state,
            leagues,
            new_items_only=True
        )

    save_state(state)
    
    state = validate_state(state)
    save_state(state)

if __name__ == "__main__":
    main()
