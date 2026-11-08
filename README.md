# 🎉 Party Portal

**The whole world's party, live, right now** — live world party cams, Cercle and festival DJ sets, pool and
beach parties, swim-week runways, retro MTV, rock and hip-hop live, a worldwide party calendar and real
nightlife news.

> Live at: `https://theseanmitchell.github.io/PartyPortal/`

A fast, single-page, static site (no framework, no server). See **[CHANGELOG.md](CHANGELOG.md)** for the
full 3.0 notes.

---

## Features

- **Two looks, one switch** — the colourful **Neon** look (default) and **Onyx** dark mode, identical to
  NUZU's dark mode and Argus Onyx. The *Dark* switch in the top bar (or the `T` key) remembers your choice
  (`localStorage 'pp:theme'`); a link can force one with `?theme=dark` or `?theme=light`.
- **1,700+ verified videos in ~390 playlist channels across 19 lanes** — Live World Cams, Cercle & Scenic, Festival Mainstage, Club &
  Boiler Room, Pool & Beach Parties, Swim & Bikini Runway, Fashion Week Runway, Retro MTV & Spring Break,
  Rock Live, Hip-Hop Live, Latin & Reggaeton, Carnival & Street Parties, Melodic Techno, Anjuna Open Air,
  Afro House, Psytrance, Rave/DnB/Hard Techno, Arena Concerts, 24/7 Radio. Every video comes from the
  official channel of the event, venue, label, broadcaster or artist, embeds on this site, is not
  age-restricted, and is long-form (or actually live, for cams and radio).
- **A different wall every visit** — channels are playlists of ~6 videos; each starts on a random video
  this device hasn't seen lately. A theme-weighted shuffle across all lanes (at most 2 tiles per lane) and
  a per-device memory of recent channels and videos keep consecutive visits different (10 test visits:
  100 tiles, 100 different videos). Long sets start at a random point.
- **Stations** — one chip per lane with a live count, plus ★ Favorites. Keys **1–9** jump to the first nine.
- **Search**, **favorites** (⭐, saved on your device), **share / deep-link** (`?ch=<id>` features a channel).
- **Party Mode** — full-screen 12-channel wall (desktop). **Mobile player** — one channel at a time with
  swipe, shuffle and auto-advance.
- **On The Horizon** — festivals with countdowns (gold shimmering cards) plus club, dayclub, concert and
  residency dates from Las Vegas, Miami, Los Angeles, New York, London, Ibiza and more. Filter by
  **When / Where / Type**, scroll with the ‹ › buttons, arrow keys, drag or wheel, or open **View all**.
- **Party & Culture News** — real headlines from ~110 music, nightlife, fashion and culture outlets in 12
  tabs with counts, refreshed 3×/day.
- **Installable PWA** + offline support, keyboard shortcuts (`?` for the list), social share card.

---

## How the content stays fresh (no API keys needed)

`.github/workflows/daily-content.yml` runs at **06:00, 12:00, 18:00 UTC** (and on manual dispatch):

1. **`bot.py`** writes `feed.json` (news) and `events.json` (calendar). News comes from Google News `site:`
   feeds of trusted outlets plus a few publishers' own RSS; titles are cleaned, promo/service posts
   (ticket how-tos, promo codes, betting, horoscopes, puzzle answers, shopping deals, press-release wires)
   and hard news are filtered out, near-duplicates merged, each outlet capped per day. Nothing is ever
   invented: if nothing real passes, the old file stays.
2. **`curate.py`** checks every channel in `channels.json` (YouTube oEmbed for videos, the public watch
   page for live cams/radio, playlist pages for playlists), drops dead ones (offline live streams after
   2 runs in a row), and refills Live World Cams from official cam operators when that lane runs low.
   A sanity gate refuses to write if a run would drop more than 15% at once.

Optional secrets: `YOUTUBE_API_KEY` (extra growth from official channels) and `TICKETMASTER_API_KEY`
(more concert dates). Both are optional; without them everything above still runs.

Run locally: `python bot.py` and `python curate.py` (Python 3.8+, standard library only).

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `S` | Shuffle channels |
| `P` | Party Mode (desktop) |
| `F` | Show only favorites |
| `1`–`9` | Jump to a station |
| `/` | Search channels |
| `T` | Dark (Onyx) / Neon |
| `?` | Help / shortcuts |
| `Esc` | Close / exit |

---

## Adding a channel

Add a line to `channels.json` (one channel per line):

```json
{"id":"cercle-myset","cat":"CERCLE","maxIdx":1,"label":"🏔️ Artist — Place","embed":"https://www.youtube.com/embed/VIDEO_ID","src":"Cercle","len":5400}
```

`cat` is one of `LIVE CAM, CERCLE, FESTIVAL, CLUB, POOL, SWIM, FASHION, RETRO, ROCK, HIPHOP, LATIN,
CARNIVAL, MELODIC, ANJUNA, AFRO, PSYTRANCE, RAVE, CONCERT, RADIO`. `len` (seconds) lets long sets start at a
random point; add `"live":true` for live streams. Use only uploads from the official channel, and check the
video plays when embedded. `curate.py` removes it automatically if it ever dies.

## Adding a news source or keyword

In `bot.py`, add a row to `NEWS_SOURCES` — `(name, feed url, home tab)`; `site("domain.com")` builds the
Google News feed — and short, high-signal words to `RAW_KEYWORDS` (relevance) or `RAW_TAB_KEYWORDS`
(which tab a story lands in). Specialist outlets can go in `NICHE_SOURCES` to pass without a keyword.

## Adding a calendar date

Big festivals live in `FESTIVALS` in `bot.py` with the dates their organisers announced (an edition drops
off by itself after it ends). Any venue page that publishes schema.org Event data can be added to
`VG_JSONLD_SOURCES` or `CAL_SOURCES`.

---

## Deploy (GitHub Pages)

1. Push to `TheSeanMitchell/PartyPortal`.
2. Settings → Pages → deploy from `main` (root).
3. Live at `https://theseanmitchell.github.io/PartyPortal/`.

---

*Built with ❤️ in Las Vegas by Mitchell Sean Vasseur*
