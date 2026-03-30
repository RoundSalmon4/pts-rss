
import requests
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "state.json"
RSS_FILE = ROOT / "rss.xml"

LEAGUE_URL = "https://plaintextsports.com/nba/"
FEED_TITLE = "Plain Text Sports – NBA Finals"
FEED_LINK = LEAGUE_URL

HEADERS = {
    "User-Agent": "plaintextsports-rss/1.0 (GitHub Pages)"
}

def load_state():
    if not STATE_FILE.exists():
        return {"published_games": []}
    return json.loads(STATE_FILE.read_text())

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def fetch_page():
    return requests.get(LEAGUE_URL, headers=HEADERS, timeout=20).text

def extract_final_games(text):
    lines = text.splitlines()
    finals = []
    score_line = re.compile(r"\|\s+([A-Z]{2,3})\s+(\d+)")

    for i, line in enumerate(lines):
        if "Final" in line:
            window = lines[i-3:i+3]
            teams = []
            for l in window:
                m = score_line.search(l)
                if m:
                    teams.append((m.group(1), m.group(2)))
            if len(teams) == 2:
                finals.append({"away": teams[0], "home": teams[1]})
    return finals

def build_rss(new_items):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = FEED_TITLE
    SubElement(channel, "link").text = FEED_LINK
    SubElement(channel, "description").text = "NBA final scores from Plain Text Sports"

    if RSS_FILE.exists():
        tree = ElementTree()
        tree.parse(RSS_FILE)
        old_items = tree.getroot().find("channel").findall("item")
        for item in old_items:
            channel.append(item)

    for game in new_items:
        item = SubElement(channel, "item")
        title = f"{game['away'][0]} {game['away'][1]} – {game['home'][0]} {game['home'][1]} (Final)"
        SubElement(item, "title").text = title
        SubElement(item, "link").text = FEED_LINK
        SubElement(item, "guid").text = game["id"]
        SubElement(item, "pubDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    ElementTree(rss).write(RSS_FILE, encoding="utf-8", xml_declaration=True)

def main():
    state = load_state()
    html = fetch_page()
    finals = extract_final_games(html)
    new_items = []

    for g in finals:
        game_id = f"nba-{g['away'][0]}-{g['home'][0]}-{datetime.utcnow().date()}"
        if game_id not in state["published_games"]:
            g["id"] = game_id
            new_items.append(g)
            state["published_games"].append(game_id)

    if new_items:
        build_rss(new_items)
        save_state(state)

if __name__ == "__main__":
    main()
