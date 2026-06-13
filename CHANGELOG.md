# Changelog

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
