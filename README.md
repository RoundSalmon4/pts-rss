
# Plain Text Sports – Advanced RSS Feeds

This repository auto-generates RSS feeds from **PlainTextSports.com**.

## Feeds Generated

### League feeds
- `/rss/nba.xml`
- `/rss/mlb.xml`
- `/rss/nhl.xml`
- `/rss/nfl.xml`

### Team feeds (auto-created)
- `/rss/teams/<league>-<team>.xml`
  - Example: `/rss/teams/nba-lal.xml`

### Combined feed
- `/rss/all-finals.xml`

## Behavior
- One item per game
- Published once, when the game goes FINAL
- OT games are marked `(OT)` in the title
- pubDate is UTC (RSS-safe)

Updated automatically by GitHub Actions every 10 minutes.
