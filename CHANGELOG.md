# Changelog

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
