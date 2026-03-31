
import requests, json, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
from bs4 import BeautifulSoup

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
    return json.loads(STATE_FILE.read_text())

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def fetch(url):
    print(f"Fetching: {url}")
    response = requests.get(url, headers=HEADERS, timeout=20)
    print(f"Status: {response.status_code}, Length: {len(response.text)}")
    return response.text

def extract_games(html):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    links = soup.find_all("a", href=True)
    print(f"Found {len(links)} total links")
    for game in links:
        href = game.get("href", "")
        if "/20" not in href:
            print(f"  SKIP link (no /20): {href}")
            continue
        print(f"  GAME LINK: {href}")
        text = game.get_text()
        print(f"    text: {repr(text[:200])}")
        if "Final" not in text:
            print(f"    NO 'Final' - skipping")
            continue
        team_scores = re.findall(r"([A-Z]{2,3})\s+(\d+)", text)
        if len(team_scores) == 2:
            ot = "OT" in text
            games.append(((team_scores[0][0], team_scores[0][1]), (team_scores[1][0], team_scores[1][1]), ot))
            print(f"    ADDED: {team_scores}")
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

def write_feed(path, title, link, description, new_items):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description

    for item in load_existing_items(path):
        channel.append(item)

    for gid, txt in new_items:
        it = SubElement(channel, "item")
        SubElement(it, "title").text = txt
        SubElement(it, "link").text = link
        SubElement(it, "guid").text = gid
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

    for league, url in leagues.items():
        state["published"].setdefault(league, [])
        league_new = []

        for date_str in [today, yesterday, two_days_ago, three_days_ago]:
            if date_str == today:
                check_url = url
            else:
                check_url = f"{url}{date_str}/"
            
            print(f"Checking {league} {date_str}: {check_url}")
            html = fetch(check_url)
            games = extract_games(html)
            print(f"  Games from {date_str}: {games}")

            for away, home, ot in games:
                gid = f"{league}-{away[0]}-{home[0]}-{date_str}"
                if gid in state["published"][league]:
                    continue
                suffix = " (OT)" if ot else ""
                title = f"{away[0]} {away[1]} – {home[0]} {home[1]} (Final){suffix}"
                state["published"][league].append(gid)
                league_new.append((gid, title))
                all_new.append((gid, f"{league.upper()}: {title}"))
                for team in (away[0], home[0]):
                    team_path = TEAM_DIR / f"{league}-{team.lower()}.xml"
                    write_feed(team_path, f"{league.upper()} – {team} Finals", url, f"Final games for {team}", [(gid, title)])

        if league_new:
            write_feed(
                RSS_DIR / f"{league}.xml",
                f"Plain Text Sports – {league.upper()} Finals",
                url,
                f"{league.upper()} final scores",
                league_new
            )
        else:
            write_feed(
                RSS_DIR / f"{league}.xml",
                f"Plain Text Sports – {league.upper()} Finals",
                url,
                f"{league.upper()} final scores",
                [(f"{league}-placeholder", "No games available currently")]
            )

    if all_new:
        write_feed(
            RSS_DIR / "all-finals.xml",
            "Plain Text Sports – All Finals",
            "https://plaintextsports.com",
            "All leagues final scores",
            all_new
        )
    else:
        write_feed(
            RSS_DIR / "all-finals.xml",
            "Plain Text Sports – All Finals",
            "https://plaintextsports.com",
            "All leagues final scores",
            [("all-placeholder", "No games available currently")]
        )

    save_state(state)

if __name__ == "__main__":
    main()
