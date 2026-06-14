# 🎉 Party Portal

**Your One-Stop Party Destination** — live festival streams, party cams, nightlife feeds, and real party-culture news.

> Live at: `https://theseamitchell.github.io/PartyPortal`

A fast, single-page, static site (no framework, no server). See **[CHANGELOG.md](CHANGELOG.md)** for the full v2.0 upgrade notes.

---

## Features

- **125+ live channels** — EDM festivals, DJ sets, retro MTV, rock blocks, 24/7 city cams, plus deep lanes: **Cercle** & **Anjuna** (official 4K landmark sets), **Psytrance** (Ozora/Boom full sets), **Pool Party** day-club sets, **Melodic** techno, **Afro House**, and **Rave** mixes.
- **Stations & filters** — tune the wall by category (Festivals, Clubs, Cercle, Anjuna, Melodic, Afro House, Rave, Live Cams, …) or fire a curated mix: **🔥 Peak Hours**, **🌌 Immersive**, **📼 Throwback**. Each chip shows a live count. Press **1–9** to jump between stations.
- **Share / deep-link** — 🔗 on any tile copies a `?ch=<id>` link (or opens the native share sheet); opening it features that channel.
- **Favorites** — ⭐ any channel; saved on your device, filterable, one tap away.
- **Channel search** — type to find a channel by name.
- **Per-tile controls** (desktop) — unmute (auto-mutes the rest), fullscreen, favorite. Click a tile to unmute.
- **Party Mode** — full-screen 12-channel video wall (desktop).
- **Mobile player** — one channel at a time: **Prev / Shuffle Next**, swipe to change, tap to unmute, optional auto-advance. *(No Party Mode on mobile.)*
- **Festival countdowns** — live timers + ticket links to the next confirmed 2026 festivals.
- **Culture feed** — **real** headlines from the music & nightlife press, refreshed 3×/day.
- **Installable PWA** + offline support, keyboard shortcuts (`?` for the list), social share card.

---

## How the news works (real data only)

The culture feed is **100% real**. `bot.py` gathers headlines from trusted publications
(Mixmag, DJ Mag, Resident Advisor, EDM.com, Dancing Astronaut, Billboard, Rolling Stone,
Pitchfork, NME, …) via public Google News feeds, then:

1. uses `site:` queries to pull straight from those domains,
2. strips the trailing " - Source" from each title,
3. drops junk/spam (tracking-code titles, daily-digest pages, mashups),
4. filters out off-topic and negative content (specialist EDM sources pass on-topic; broad
   outlets must match a party keyword),
5. tags a source-trust tier (green/amber/grey dot), de-duplicates, and
6. writes `feed.json` only.

If nothing real passes the filters, `feed.json` is left untouched — the site **never** shows
invented headlines. The page links every headline to its original publisher.

The bot runs on GitHub Actions at **06:00, 12:00, 18:00 UTC** (and on manual dispatch). Run it
locally with `python bot.py` (Python 3.8+, standard library only).

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `S` | Shuffle channels |
| `P` | Party Mode (desktop) |
| `F` | Show only favorites |
| `/` | Search channels |
| `?` | Help / shortcuts |
| `Esc` | Close / exit |

---

## Adding a channel

Add an entry to `PP_ALL_FEEDS` in `index.html`:

```javascript
{
  id:    'myfest',                 // unique slug
  cat:   'FESTIVAL',               // FESTIVAL | CLUB | ARTIST | ROCK | RETRO | CONCERT | RADIO | FASHION | LIVE CAM
  maxIdx: 1,                       // playlist length (1 for a single video)
  label: '🎪 My Festival Name',
  embed: 'https://www.youtube.com/embed/VIDEO_ID',   // or videoseries?list=PLAYLIST_ID
  url:   'https://official-site.com'                 // optional: shown as "Official site / Tickets"
}
```

New categories automatically get their own filter chip.

---

## Adding a news source or keyword

In `bot.py`, add to `RAW_KEYWORDS` and/or `CULTURE_SOURCES`:

```python
RAW_KEYWORDS += ["your festival name", "new venue"]

CULTURE_SOURCES += [
    ("My Source", g("site:mysource.com+when:3d")),   # g() builds the Google News RSS URL
]
```

Specialist EDM domains can be added to `NICHE_SOURCES` to accept them on-topic without a keyword match.

---

## Deploy (GitHub Pages)

1. Push to `TheSeanMitchell/PartyPortal`.
2. Settings → Pages → deploy from `main` (root). A `.nojekyll` file is included so every asset
   (`feed.json`, `sw.js`, `manifest.webmanifest`, icons) is served as-is.
3. Live at `https://theseamitchell.github.io/PartyPortal`.

---

*Built with ❤️ in Las Vegas*
