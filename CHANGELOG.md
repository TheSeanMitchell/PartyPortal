# Changelog

## v2.6 — Autonomous channel agent, EARLIER finally fixed, gold rails, US festivals

### Channel automation (the road to 999, hands-free)
- New **`curate.py`** agent runs in the daily Action. With a `YOUTUBE_API_KEY` it:
  - **Prunes** dead / private / non-embeddable / **under-2-minute** / low-view videos (kills the 45-second-promo problem) — never touching live cams, radio, or playlists.
  - **Grows** the catalogue by searching on-theme queries for **long-form** (>20 min), embeddable, popular sets and adding a few new channels per run, deduped, toward a 999 cap.
- Channels now live in **`channels.json`** so the agent can edit them. `index.html` loads it and **falls back to its built-in list if anything's off**, so the wall can never break. Hard sanity gates + a `.bak` backup protect against bad runs.
- **To activate:** add a `YOUTUBE_API_KEY` repo secret (free Google Cloud key). Without it the agent no-ops and nothing changes.

### Victoria's Secret short-clip fix
- Removed the VS playlist that was surfacing 45-second promos. The full **VS 2025 show (4K)**, **VS Swim Special**, and **SI Swimsuit** runways remain — all long-form. (Once the agent is on, this kind of thing gets caught automatically.)

### News — EARLIER actually works now
- The real bug: the per-source cap I added was keeping each outlet's **5 newest** items (all today), so yesterday got deleted every run. Fixed with a **per-source-per-day** cap (each outlet can fill both days) plus a **balanced two-day selection** — verified yesterday now survives a today-heavy flood.
- Strengthened the party-positive filter: deaths, shootings, crashes, and court/feud noise are now blocked (the screenshot's Oliver Tree and pool-shooting items are gone).

### Calendar + polish
- Added 6 major **US festivals** to On The Horizon: Outside Lands, HARD Summer, North Coast, Imagine, Lost Lands, Portola (gold cards, ticket links).
- Theme/naming pass: retired generic names like "Rock N Roll Channel #2" → "Rock N' Roll — Encore," "Retro Rock — Deep Cuts," "EDM Radio — Underground," etc.

## v2.5 — Gold mega-events, news source overhaul + working EARLIER, playlists & random-start

### "On The Horizon" — mega events get the gold treatment
- Festivals and **headliner** Vegas shows (Deadmau5, Marshmello, Chainsmokers, Odesza, Diplo, Kaskade, Don Toliver, Meek Mill, Tiësto, Martin Garrix, and ~40 more) now render in a **gold, shimmering card** with a ★ and a "Headliner" tag — clearly special vs. the routine nightly events.
- The standalone **Vegas Nightlife** directory section was **removed** — those events now live in the unified On The Horizon feed, so it was redundant.

### News feed — real fix for EARLIER + source diversity
- **EARLIER now works like NUZU.** The column was empty because the UI bucketed by a rolling 24-hour window; it now buckets by **calendar day** (your local time), so yesterday's stories show up immediately (and are ranked by how many sources covered them).
- **Source flooding fixed.** One outlet (Resident Advisor) was filling 34 of 55 slots. Added a **per-source cap** (max 5 per outlet) with **regional-subdomain normalization** (fr/de/es.ra.co all count as one), so no single source dominates — and yesterday's stories stop getting pushed off the list.
- **Way more sources.** The roster went from ~31 to **48 outlets** spanning EDM, rock, hip-hop, festivals, and nightlife (Loudwire, Ultimate Classic Rock, Brooklyn Vegan, Consequence, HipHopDX, EDM Identity, EDM Sauce, Data Transmission, When We Dip, Ibiza Spotlight, Music Festival Wizard, Time Out, and more).
- **Tighter on-topic filtering + better categories.** Expanded the keyword/blocklist (drops court/feud/health/politics noise) and added **Vegas, Rock, and Hip-Hop** news categories so the feed mirrors the whole site.

### Channels — playlists + random start (no more stale revisits)
- Non-live channels start on a **random video** on each load; bumped the Encore Beach Club playlist and added official **playlist** channels that auto-rotate: **Tomorrowland 2025 Live Sets (99 sets)**, Tomorrowland 2022, a Monstercat/NCS bass mix, and UKF Drum & Bass. Playlists also self-heal if any single video gets removed.
- 126 → **131 channels**.

## v2.4 — Live Vegas events in "On The Horizon" + clickable event cards, Summer Fashion

### Vegas events feed (the big one)
- **Every Strip club & dayclub event now flows into "On The Horizon"**, merged chronologically with the festival countdowns — one unified upcoming-events feed, soonest first. Real lineups scraped from No Cover Nightclubs (Zouk, XS, Omnia, Marquee, Tao, Hakkasan, LIV, Jewel, Encore Beach Club, Marquee Dayclub, Tao Beach, Liquid, Palm Tree, LIV Beach, AYU, Tailgate + EBC At Night).
- **Each event is a clickable digital card** → opens a detail modal with the artist, venue, date/time, a **🎟️ Guest List & Tickets** button (straight to the event's No Cover page), a **▸ Watch** button (plays the artist on the wall if we have a matching channel, otherwise opens a YouTube set search), and an **About the artist** link.
- **Live + self-updating.** `bot.py` now scrapes all 16 venue calendars on every run (3×/day) and writes `events.json`; the GitHub Action commits it. Parsing is done off the event URL slugs (artist + venue + date), so it survives any page redesign. Seeded with 37 real events (Jun 13 – Jul 31, 2026); past events auto-drop, new ones roll in.
- The **Vegas Nightlife** venue directory from v2.3 stays as a quick "jump to a venue's calendar" strip.

### Summer Fashion
- The Fashion lane is now **Summer Fashion** and added 4 marquee swim/runway shows: **SI Swimsuit** Miami Swim Week 2024 + Swim Week 2025, **Victoria's Secret** The Show 2025 (4K), and the **VS Swim Special**. (Also fixed a duplicate Victoria's Secret tile.) Picked for being the most iconic, highest-production shows.

### Under the hood
- `events.json` carries a `city` field, so non-Vegas / nationwide concerts can be dropped in later (a Ticketmaster/Bandsintown key would let the bot pull those automatically).
- 122 → **126 channels**.

## v2.3 — Psytrance + Pool Party channels, NUZU-style news, Vegas nightlife, mute toggle

### New channel types (106 → 122)
- **🍄 Psytrance (new, 13)** — official *Full Set Movies* from Astrix, Ace Ventura and Liquid Soul at **Ozora** and **Boom Festival** (high-quality video + audio, stable official uploads). Added to the **🔥 Peak Hours** station.
- **🏖️ Pool Party (new, 4)** — daytime/poolside sets & aftermovies: your pick, Ushuaïa Ibiza (Opening 2025 + 2025 aftermovie), and an Encore Beach Club Las Vegas playlist.
- Removed the Keinemusik afro tile that got copyright-claimed (the "video unavailable" one).

### News feed — now styled like NUZU
- **Source logos** — every headline now shows the publisher's favicon (via the bot capturing each story's domain), with the 2-letter monogram as a fallback.
- **"🔥 N sources" ranking** — the bot clusters the same story across outlets and counts how many distinct sources reported it; the most-reported stories are badged and sorted to the top of each column.
- **Yesterday's biggest stories** — the bot now *merges the previous feed* on every run (48-hour window), so the **Earlier** column keeps yesterday's top stories instead of emptying out. (The Earlier column fills in automatically after the next scheduled bot run, since it needs a prior day of data to carry forward.)

### Vegas Nightlife directory
- New **Vegas Nightlife** section: 17 Strip clubs & pool parties (Zouk, XS, Omnia, Marquee, Tao, Hakkasan, LIV, Jewel, EBC + the dayclubs), each linking straight to its live **guest list** and **event calendar** on No Cover Nightclubs — always-current event links rather than dates that go stale.

### Fixes
- **You can re-mute now.** Clicking an unmuted tile (or the speaker button) toggles it back to muted, so you're no longer forced to keep audio playing on *some* channel. The auto-mute-others behaviour and auto-mute-on-new-channel are unchanged — works the same in Party Mode too.

## v2.2 — Big scenic-channel expansion + Vegas + fixes

### Channels (70 → 106)
- **+36 verified high-quality channels**, weighted to the scenic/immersive "Cercle vibe" (real, embeddable, mostly official 4K video with great audio):
  - **Cercle (+13)** — Ben Böhmer above Cappadocia, Boris Brejcha (Nîmes / Grand Palais / Fontainebleau), Sébastien Léger at the Pyramids, Tale Of Us & Stephan Bodzin at Piz Gloria, Jan Blomqvist at Tossa de Mar, Nina Kraviz at the Eiffel Tower, Maceo Plex on the Hudson, Amelie Lens at the Atomium, and more.
  - **Anjuna (+17, new category)** — official Anjunadeep / Above & Beyond open-air 4K sets (Ben Böhmer, Jody Wisternoff, Yotto, Eli & Fur, Marsh at Red Rocks, A&B Group Therapy).
  - **Afro House (+4, new category)** — Black Coffee / Keinemusik–style soulful sets.
  - **Melodic / Festival (+2)** — another Afterlife set and Dimitri Vegas & Like Mike's Tomorrowland 2025 mainstage.
- New chips for **Anjuna** and **Afro House**; **🌌 Immersive** station now spans Cercle + Melodic + Anjuna.

### "On The Horizon" — Las Vegas added (11 → 14)
- **iHeartRadio Music Festival** — Sep 18–19, T-Mobile Arena.
- **Metallica · Sphere** ("Life Burns Faster") — opens Oct 1.
- **F1 Las Vegas Grand Prix** — Nov 19–21, Las Vegas Strip.
- (Most other Sphere/club residencies have already wrapped for 2026; these are the confirmed upcoming marquee Vegas dates.)

### Fixes
- **YouTube controls were getting clipped in Party Mode.** The full-wall tiles were zoomed ~5% from their *center*, which cropped the top and bottom — and YouTube's volume slider lives at the bottom. The zoom is now anchored to the bottom edge, so the control bar (and volume slider) stays fully visible. Overlay labels also fade out on hover in both the wall and the main grid so they never sit over the player controls.
- **The archive.org clip wouldn't muted-autoplay** (browsers block unmuted autoplay and archive's player has no reliable mute flag). Replaced it with a real YouTube MTV Spring Break 2000 clip, so it now behaves exactly like every other tile.

## v2.1 — Channel expansion + ergonomics

### Channels (49 → 70)
- **+21 verified channels** across three new categories, each with real, embeddable, long-stable YouTube IDs:
  - **Cercle** (7) — scenic live DJ sets filmed at landmark locations (Above & Beyond in Guatapé, ARTBAT & Monolink at Cercle Odyssey, Argy at Jungfraujoch, Black Coffee, FKJ at the Bolivian salt flats, Disclosure b2b Mochakk).
  - **Melodic** (7) — Afterlife / Anyma-style immersive melodic techno, incl. the 4K drone Afterlife Budapest set.
  - **Rave** (7) — future-rave, big-room, hard-trance and trance-classics mixes, plus a rotating Future-Rave playlist.
- Two new station presets: **🌌 Immersive** (Cercle + Melodic) and Rave folded into **🔥 Peak Hours**.

### "On The Horizon" (4 → 11 festivals)
- Widened to 11 confirmed upcoming 2026 festivals with live countdowns + ticket links: Defqon.1, Ultra Europe, Tomorrowland, Lollapalooza, Untold, Sziget, Creamfields, Mysteryland, Burning Man, Ultra Japan, EDC Orlando. (Dates verified; fallow/past events excluded.)
- Countdown cards for festivals we stream (Tomorrowland, Ultra, Creamfields, EDC) are now **clickable to filter the wall** to that festival's channels.

### New standalone features
- **Share / deep-link** — every tile (and the mobile player) has a 🔗 share button that copies a `?ch=<id>` link or opens the native share sheet. Opening that link **features that channel** first.
- **Remembers your station** — your last selected station is restored on return (localStorage).
- **Number keys 1–9** jump straight to a station.
- **News category pills** — filter the culture feed by Festival / EDM / Nightlife / Concert / Culture / Fashion, with live counts.

### News quality
- **Near-duplicate clustering** in `bot.py`: collapses multiple rewrites of the same story (Jaccard ≥ 0.55 on significant words), keeping the highest-trust source — no more five-in-a-row repeats.

## v2.0 — Major upgrade

A theme-preserving overhaul. Same neon Party Portal look; lots more under the hood.

### Requested
- **New favicon** — a custom neon "portal" mark (gradient ring + live play triangle).
  Ships as `favicon.svg`, `favicon.ico`, `favicon-16/32.png`, plus `apple-touch-icon.png`
  and maskable PWA icons (`icon-192.png`, `icon-512.png`). Previously the site had **no**
  favicon at all.
- **Mobile = one channel at a time.** Below 600px the multi-video grid is replaced by a
  single full-width player with **Prev / Shuffle-Next**, swipe-to-change, a tap-to-unmute
  button, an optional auto-advance toggle, and a favorite star. **Party Mode is hidden on
  mobile.** (Before, mobile showed *no* video at all — the grid was simply `display:none`.)
- **Real news only.** Removed the hardcoded synthetic `FALLBACK` headlines from the page.
  The culture feed now renders strictly from `feed.json`; if it can't load, it shows an
  honest empty state with a retry button — never fake stories.

### News pipeline (rewritten `bot.py`, NUZU-grade)
- Pulls from trusted music/nightlife press using `site:` queries (Mixmag, DJ Mag, Resident
  Advisor, EDM.com, Dancing Astronaut, Billboard, Rolling Stone, Pitchfork, NME, and more)
  plus targeted festival / nightlife / city searches.
- Strips the trailing " - Source Name" from every headline.
- **Junk/spam filter:** drops tracking-code titles (e.g. `(Ys2A1erDKV)`), daily-digest /
  "print edition" pages, and absurdly long mashups.
- **Relevance gate:** specialist EDM outlets are accepted on-topic; broad outlets must match
  a party-culture keyword — this kills the celebrity/chart noise the old feed let through.
- **Source-trust tiers** (1/2/3) drive a small green/amber/grey dot next to each source.
- Writes `feed.json` only (never edits `index.html`); writes nothing if no real items pass.
- The shipped `feed.json` was re-cleaned from the existing real data (40 noisy → 10 on-topic).

### New features (all theme-consistent)
- **Stations & category filters** — All, Favorites, plus per-category chips (Festivals,
  Clubs, Artists, Rock, Retro, Concerts, Live Cams, Radio, Fashion) and two curated mixes:
  **🔥 Peak Hours** (Festival + Club) and **📼 Throwback** (Retro + Rock). Live counts on each.
- **Favorites** — star any channel; saved on-device (localStorage), filterable, one-tap.
- **Channel search** — type to filter the wall / mobile queue by name.
- **Per-tile controls** (desktop) — unmute (with auto-mute of the others), fullscreen, and
  favorite, on hover. Click any tile to unmute it.
- **Festival countdowns** — live ticking timers to confirmed 2026 festivals (Tomorrowland,
  Lollapalooza, Creamfields, Burning Man) with official ticket links. Glastonbury was
  intentionally excluded (2026 is its fallow year).
- **Keyboard shortcuts** — `S` shuffle, `P` Party Mode, `F` favorites, `/` search, `?` help,
  `Esc` close. A help overlay documents them.
- **Installable PWA** — web manifest, service worker, offline fallback page; an "Install"
  button appears when the browser offers it.
- **SEO/social** — Open Graph + Twitter Card meta, a branded 1200×630 share image
  (`og-image.png`), canonical URL, and JSON-LD.
- **Accessibility** — visible keyboard focus, `prefers-reduced-motion` support, ARIA labels.
- **New pages** — real `about.html`, `privacy.html`, `contact.html` (footer links used to be
  dead `#` anchors).
- **Hosting fix** — added `.nojekyll` and corrected `_config.yml` so `feed.json` and all
  assets are served (the old config excluded `feed.json`, which the page needs to fetch).

### Preserved
- The full neon visual identity, the 49-channel pool, the Party Mode video-wall packing
  algorithm, the culture ticker, and the TODAY/EARLIER news layout.
