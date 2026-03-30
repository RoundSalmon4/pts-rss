
import requests, json, re
from pathlib import Path
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "state.json"
RSS_DIR = ROOT / "rss"
TEAM_DIR = RSS_DIR / "teams"

LEAGUES = {
    "nba": "https://plaintextsports.com/nba/",
    "mlb": "https://plaintextsports.com/mlb/",
    "nhl": "https://plaintextsports.com/nhl/",
    "nfl": "https://plaintextsports.com/nfl/",
}

HEADERS = {"User-Agent": "plaintextsports-rss/3.0"}
SCORE_RE = re.compile(r"\|\s+([A-Z]{2,3})\s+(\d+)")

RSS_DIR.mkdir(exist_ok=True)
TEAM_DIR.mkdir(parents=True, exist_ok=True)

def load_state():
    if not STATE_FILE.exists():
        return {"published": {}}
    return json.loads(STATE_FILE.read_text())

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def fetch(url):
    return requests.get(url, headers=HEADERS, timeout=20).text.splitlines()

def extract_games(lines):
    games = []
    for i, line in enumerate(lines):
        if "Final" in line:
            ot = "OT" in line
            teams = []
            for w in lines[i-4:i+4]:
                m = SCORE_RE.search(w)
                if m:
                    teams.append(m.groups())
            if len(teams) == 2:
                games.append((teams[0], teams[1], ot))
    return games

def load_existing_items(path):
    if not path.exists():
        return []
    return ElementTree(file=path).getroot().find("channel").findall("item")

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
        SubElement(it, "pubDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    ElementTree(rss).write(path, encoding="utf-8", xml_declaration=True)

def main():
    state = load_state()
    state.setdefault("published", {})
    all_new = []

    for league, url in LEAGUES.items():
        state["published"].setdefault(league, [])
        lines = fetch(url)
        games = extract_games(lines)
        league_new = []

        for away, home, ot in games:
            gid = f"{league}-{away[0]}-{home[0]}-{datetime.utcnow().date()}"
            if gid in state["published"][league]:
                continue

            suffix = " (OT)" if ot else ""
            title = f"{away[0]} {away[1]} – {home[0]} {home[1]} (Final){suffix}"
            state["published"][league].append(gid)

            league_new.append((gid, title))
            all_new.append((gid, f"{league.upper()}: {title}"))

            for team in (away[0], home[0]):
                team_path = TEAM_DIR / f"{league}-{team.lower()}.xml"
                write_feed(
                    team_path,
                    f"{league.upper()} – {team} Finals",
                    url,
                    f"Final games for {team}",
                    [(gid, title)]
                )

        if league_new:
            write_feed(
                RSS_DIR / f"{league}.xml",
                f"Plain Text Sports – {league.upper()} Finals",
                url,
                f"{league.upper()} final scores",
                league_new
            )

    if all_new:
        write_feed(
            RSS_DIR / "all-finals.xml",
            "Plain Text Sports – All Finals",
            "https://plaintextsports.com",
            "All leagues final scores",
            all_new
        )

    save_state(state)

if __name__ == "__main__":
    main()
