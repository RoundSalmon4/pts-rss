
# Plain Text Sports – RSS Feeds

This repository auto-generates RSS feeds from **PlainTextSports.com**.

## Features

- **Auto-discovery** - Automatically finds all sports available on PlainTextSports.com
- **Real-time updates** - Games appear within minutes of going final
- **Team-specific feeds** - Separate feeds for each team

## Feeds Generated

### League feeds
- `/rss/<league>.xml` (e.g., `/rss/nba.xml`, `/rss/mlb.xml`)

### Team feeds (auto-created)
- `/rss/teams/<league>-<team>.xml`
- Example: `/rss/teams/nba-lal.xml`

### Combined feed
- `/rss/all-finals.xml`

## Supported Sports

The script auto-discovers available sports. Current sports include:
- NBA
- MLB
- NHL
- NFL
- WNBA
- NCAA Men's Basketball
- NCAA Women's Basketball
- UEFA Champions League
- UEFA Europa League
- Premier League
- MLS
- NWSL

## Behavior

- One item per game
- Published immediately when the game goes FINAL
- OT games are marked `(OT)` in the title
- pubDate is UTC (RSS-safe)
- Updated automatically by GitHub Actions every 10 minutes
