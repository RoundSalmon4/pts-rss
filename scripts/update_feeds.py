
import requests, json, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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

def load_state():
    if not STATE_FILE.exists():
        return {"published": {}}
    data = json.loads(STATE_FILE.read_text())
    for league, items in data.get("published", {}).items():
        if isinstance(items, list):
            new_dict = {}
            for item in items:
                new_dict[item] = ""
            data["published"][league] = new_dict
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
    
    links = soup.find_all("a", href=True)
    print(f"Found {len(links)} total links")
    for game in links:
        href = game.get("href", "")
        
        text = game.get_text()
        
        if "/20" in href:
            if "Final" not in text and "FT" not in text:
                continue
            team_scores = re.findall(r"([A-Z]{2,3})\s+(\d+)", text)
            if len(team_scores) == 2:
                ot = "OT" in text or "SO" in text
                games.append(((team_scores[0][0], team_scores[0][1]), (team_scores[1][0], team_scores[1][1]), ot))
                print(f"    ADDED from link: {team_scores}")
        else:
            if "Final" in text or "FT" in text:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                teams = []
                scores = []
                for line in lines:
                    if "Final" in line or "FT" in line:
                        continue
                    parts = line.replace("|", "").split()
                    for part in parts:
                        if re.match(r"^\d+$", part):
                            if len(scores) < len(teams):
                                scores.append(part)
                        else:
                            match = re.match(r"^(\d+)?([A-Z]{2,6})$", part)
                            if match:
                                teams.append(match.group(2))
                                if match.group(1) and len(scores) < len(teams) - 1:
                                    scores.append(match.group(1))
                if len(teams) >= 2 and len(scores) >= 2:
                    ot = "OT" in text or "SO" in text
                    games.append(((teams[0], scores[0]), (teams[1], scores[1]), ot))
                    print(f"    ADDED from ext-link: {teams[0]} {scores[0]} vs {teams[1]} {scores[1]}")
    
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
                        i += 1
                else:
                    i += 1
    
    if not games:
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 3:
                    cell_texts = [c.get_text(strip=True) for c in cells]
                    
                    score_values = []
                    teams = []
                    for text in cell_texts:
                        if re.match(r"^\d+$", text):
                            score_values.append(text)
                        elif re.match(r"^[A-Z]{2,5}$", text):
                            teams.append(text)
                    
                    if len(score_values) >= 2 and len(teams) >= 2:
                        final_idx = None
                        for i, text in enumerate(cell_texts):
                            if "Final" in text or "final" in text or "FT" in text:
                                final_idx = i
                                break
                        
                        if final_idx is not None or len(score_values) >= 2:
                            ot = "OT" in "".join(cell_texts) or "SO" in "".join(cell_texts)
                            games.append(((teams[0], score_values[0]), (teams[1], score_values[1]), ot))
                            print(f"    ADDED from table: {teams[0]} {score_values[0]} vs {teams[1]} {score_values[1]}")
    
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
            channel.append(item)

    for gid, txt in new_items:
        if gid in existing_guids:
            continue
        if state:
            for league_key, league_items in state.get("published", {}).items():
                if gid in league_items:
                    stored_title = league_items[gid]
                    if stored_title and stored_title != gid:
                        txt = f"{league_key.upper()}: {stored_title}"
                    break
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

    if league == "all":
        published = {}
        for league_guids in state.get("published", {}).values():
            published.update(league_guids)
    else:
        published = state.get("published", {}).get(league, {})

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
    two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    print(f"Today: {today}, Yesterday: {yesterday}, 2 days ago: {two_days_ago}, 3 days ago: {three_days_ago}")

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
            games = extract_games(html)
            print(f"  Games from {date_str}: {games}")
        
        cache_key = (league, date_str)
        with fetch_lock:
            games_cache[cache_key] = games
        return league, date_str, games

    fetch_tasks = []
    for league, url in leagues.items():
        for date_str in [today, yesterday, two_days_ago, three_days_ago]:
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

        for date_str in [today, yesterday, two_days_ago, three_days_ago]:
            games = games_cache.get((league, date_str), [])
            
            for away, home, ot in games:
                gid = f"{league}-{away[0]}-{home[0]}-{date_str}"
                if gid in state["published"][league]:
                    continue
                suffix = " (OT)" if ot else ""
                title = f"{away[0]} {away[1]} – {home[0]} {home[1]} (Final){suffix}"
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

if __name__ == "__main__":
    main()
