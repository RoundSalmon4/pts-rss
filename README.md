This repo is now archived please use https://github.com/RoundSalmon4/espn-rss instead.


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
- Updated automatically by GitHub Actions every 30 minutes
- All scores follow the **away – home** format (the visiting team is listed first)
- Note: PlainTextSports.com may list scores as home team first in some cases. The feeds attempt to normalize these to the away – home format when possible.
