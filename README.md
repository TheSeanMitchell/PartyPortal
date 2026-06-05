# 🎉 Party Portal

**Your One-Stop Party Destination** — live festival streams, party cams, nightlife feeds, and culture news.

> Live at: `https://theseamitchell.github.io/PartyPortal`

---

## What It Is

Party Portal is a real-time party culture hub built as a static GitHub Pages site, powered by a Python content bot that refreshes the culture feed three times daily via GitHub Actions.

### Core Features

- **25 live video channels** — EDM festivals, live cams, DJ sets, and nightlife streams
- **Randomized grid** — 10 channels are randomly selected from the pool on every page load; click **SHUFFLE** to get a new selection
- **Party Mode** — fullscreen 5×5 video wall showing all 25 channels simultaneously (identical algorithm to NUZU Waiting Room)
- **Culture ticker** — scrolling live bar at the bottom with the latest party/festival/nightlife headlines
- **Culture feed** — two-column breaking + latest news section, refreshed 3× daily by the bot

---

## Video Channel Pool (25 channels)

### 🎪 Festivals
| Channel | Category |
|---|---|
| ⚡ Electric Daisy Carnival, Las Vegas | Festival |
| 🌴 Coachella, California | Festival |
| 🌺 Coachella DJ Sets | Festival |
| 🎧 Ultra Music Fest | Festival |
| 🌍 Tomorrowland | Festival |
| ❄️ Tomorrowland Winter | Festival |
| 🇧🇷 Tomorrowland Brasil | Festival |
| 🎸 Glastonbury Classics | Festival |
| 🎨 Creamfields | Festival |
| 🌲 Lost Lands | Festival |
| 🔊 Awakenings | Festival |
| 🌙 Lucidity | Festival |
| 🎵 Day Trip | Festival |

### 🎛️ Artists / Live Sets
| Channel | Category |
|---|---|
| 💡 Pretty Lights Live | Artist |
| 🔥 Astrix Live | Artist |
| 🎼 Classmatic Live | Artist |
| 🎶 Unity Live | Artist |

### 🏖️ Clubs & Nightlife
| Channel | Category |
|---|---|
| 🏖️ Ushuaïa Ibiza | Club |

### 📻 Radio / Continuous
| Channel | Category |
|---|---|
| 🎛️ General EDM Station | Radio |
| 🎛️ General EDM Station 2 | Radio |

### 📡 Live Cams
| Channel | Category |
|---|---|
| 🎷 Bourbon Street, New Orleans, LA | Live Cam |
| ✨ The Bellagio, Las Vegas, NV | Live Cam |
| 🍺 Dublin, Ireland | Live Cam |
| 🗽 Times Square Crossroads, NYC | Live Cam |
| 🌅 Hogs Breath, Key West, FL | Live Cam |

---

## How It Works

### Static Site (GitHub Pages)
`index.html` is a single-file app — no build step, no framework, no server. It serves directly from GitHub Pages.

### Content Bot (`bot.py`)
The bot runs on GitHub Actions 3× daily:
1. Fetches RSS from 30 Google News search feeds focused on party/festival/nightlife/EDM topics
2. Filters by 200+ party-culture keywords
3. Blocklists negative/off-topic content
4. Deduplicates by normalized title hash
5. Injects `window._ppCultureItems` JSON directly into `index.html`
6. Commits the updated file back to the repo
7. GitHub Pages serves the fresh file within ~30 seconds

### Party Mode (Waiting Room Architecture)
Party Mode uses the exact same algorithm as NUZU's Waiting Room:
- `packWRGrid()` — scores every possible cols×rows layout by fill-ratio vs. overscan penalty
- `_overscan()` — applies `transform: scale()` to each iframe so YouTube's 16:9 letterboxing pushes off-screen
- Two-rAF flush cycle ensures grid is painted before measuring cells
- ESC handling distinguishes between exiting a fullscreen YouTube video vs. closing Party Mode
- Main grid iframes are blanked when Party Mode opens, restored 300ms after close

---

## Setup

### GitHub Pages
1. Push this repo to `TheSeanMitchell/PartyPortal`
2. Go to Settings → Pages → Source: **GitHub Actions** (or Branch: `main`, root `/`)
3. The site will be live at `https://theseamitchell.github.io/PartyPortal`

### Running the Bot Manually
```bash
python bot.py
```
Requires Python 3.8+ and only standard library modules (no pip installs needed).

### Bot Schedule
The bot runs automatically via GitHub Actions at:
- **06:00 UTC** (morning refresh)
- **12:00 UTC** (midday refresh)
- **18:00 UTC** (evening refresh)

You can also trigger it manually from the **Actions** tab → **Daily Culture Feed Refresh** → **Run workflow**.

---

## Adding New Videos

Add entries to the `PP_ALL_FEEDS` array in `index.html`:

```javascript
{
  id:    'myfest',                   // unique slug
  label: '🎪 My Festival Name',      // displayed on the tile
  cat:   'FESTIVAL',                 // badge: FESTIVAL | CLUB | ARTIST | RADIO | LIVE CAM
  emoji: '🎪',
  src:   'https://www.youtube.com/embed/VIDEO_ID?autoplay=1&mute=1&controls=1&modestbranding=1&rel=0&iv_load_policy=3&playsinline=1',
  wrsrc: 'https://www.youtube.com/embed/VIDEO_ID?autoplay=1&mute=1&controls=1&modestbranding=1&rel=0&playsinline=1&enablejsapi=1'
}
```

For playlists, use `videoseries?list=PLAYLIST_ID` as the embed path.
For videos that are also part of a playlist, use `VIDEO_ID?list=PLAYLIST_ID`.

---

## Adding Bot Keywords

In `bot.py`, add entries to `RAW_KEYWORDS`:
```python
RAW_KEYWORDS = [
    # ... existing keywords ...
    "your new keyword",
    "another festival name",
    "new venue name",
]
```

Add new RSS sources to `CULTURE_SOURCES`:
```python
CULTURE_SOURCES = [
    # ... existing sources ...
    ("My Source", "https://news.google.com/rss/search?q=my+search+terms+when:1d&hl=en-US&gl=US&ceid=US:en"),
]
```

---

## Roadmap

- [ ] TV / desktop Electron app wrapper
- [ ] Google Play Android app (WebView wrapper)
- [ ] User-customizable channel selection (localStorage)
- [ ] Real-time event calendar integration
- [ ] Ticketing links for detected festival headlines
- [ ] City-based nightlife sections (Vegas, Miami, NYC, Ibiza, Berlin, Dublin)
- [ ] Festival countdown timers
- [ ] Dark/light mode toggle
- [ ] PWA / service worker for offline support

---

*Built with ❤️ in Las Vegas*
