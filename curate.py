#!/usr/bin/env python3
"""
Party Portal — Channel Curation Agent
=====================================
Runs in the daily GitHub Action. Uses the YouTube Data API v3 to:

  1. PRUNE   — drop channels whose video is dead / private / non-embeddable /
               too short (< MIN_SECONDS) / low-quality. Keeps the wall from
               getting stuck on 45-second promos or "video unavailable" tiles.
  2. GROW    — search on-theme queries for long-form, embeddable, popular
               sets and add new channels (deduped), nudging the catalogue
               toward the 999-channel goal a few at a time.
  3. WRITE   — rewrites channels.json (with a .bak backup + sanity gate).

SAFETY
------
* No-ops cleanly if YOUTUBE_API_KEY is not set (the site keeps its current
  channels.json untouched).
* Never prunes LIVE CAM / RADIO / playlist channels (live streams + playlists
  don't have a normal duration and self-heal anyway).
* Only prunes a single-video channel when the API *definitively* says it's bad.
* Refuses to write if the result would drop below 80% of the current count or
  below MIN_TOTAL — so an API hiccup can't nuke the catalogue.
* index.html validates channels.json on load and falls back to its inline list
  if anything is off, so even a bad write can't break the site.

Set the GitHub secret YOUTUBE_API_KEY to activate. Tune the dials below.
"""
import os, re, json, time, urllib.parse, urllib.request

API_KEY     = os.environ.get("YOUTUBE_API_KEY", "").strip()
API         = "https://www.googleapis.com/youtube/v3/"
CHAN_FILE   = "channels.json"

# ---- dials ---------------------------------------------------------------
MIN_SECONDS = 120        # drop anything shorter than 2 minutes
MIN_VIEWS   = 5000       # quality floor for a kept/added video
MAX_ADD     = 8          # new channels added per run (gradual growth)
TARGET_MAX  = 999        # stop growing once we hit this
MIN_TOTAL   = 60         # never let the catalogue fall below this
TIMEOUT     = 20

# Growth queries: (search query, category, label prefix). videoDuration=long
# (>20 min) guarantees full sets, so grown channels are always long-form.
GROW_QUERIES = [
    ("Cercle live set full performance",            "CERCLE",    "\U0001F3AC Cercle \u2014"),
    ("Anjunadeep live dj set full",                  "ANJUNA",    "\U0001F30C Anjunadeep \u2014"),
    ("Anjunabeats trance live set full",             "ANJUNA",    "\U0001F30C Anjunabeats \u2014"),
    ("Tomorrowland mainstage full set 2025",         "FESTIVAL",  "\U0001F386 Tomorrowland \u2014"),
    ("EDC Las Vegas full dj set kineticfield",       "FESTIVAL",  "\U0001F386 EDC \u2014"),
    ("Ozora psytrance full set movie",               "PSYTRANCE", "\U0001F344 Psytrance \u2014"),
    ("Boom Festival psytrance full set",             "PSYTRANCE", "\U0001F344 Boom \u2014"),
    ("Boiler Room techno full set",                  "RAVE",      "\U0001F50A Boiler Room \u2014"),
    ("warehouse techno dj set live",                 "RAVE",      "\U0001F50A Techno \u2014"),
    ("afro house dj set live mix",                   "AFRO",      "\U0001FA98 Afro House \u2014"),
    ("melodic techno live set afterlife",            "MELODIC",   "\U0001F4A7 Melodic \u2014"),
    ("house music sunset dj set 4k",                 "CLUB",      "\U0001F3A7 House \u2014"),
    ("drum and bass live set ukf",                   "RAVE",      "\U0001F50A Drum & Bass \u2014"),
    ("classic rock live concert full show",          "ROCK",      "\U0001F3B8 Rock \u2014"),
    ("trance classics full dj set",                  "ANJUNA",    "\U0001F30C Trance \u2014"),
]
NO_PRUNE_CATS = {"LIVE CAM", "RADIO"}
_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _api(endpoint, params):
    params["key"] = API_KEY
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def parse_duration(iso):
    m = _DUR.fullmatch(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _vid_id(embed):
    """Return the video id for a single-video embed, or None for playlists."""
    if not embed or "list=" in embed or "videoseries" in embed:
        return None
    m = re.search(r"/embed/([A-Za-z0-9_-]{6,})", embed)
    return m.group(1) if m else None


def fetch_video_meta(ids):
    """Batch videos.list -> {id: {dur, embeddable, public, processed, views, live}}."""
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            data = _api("videos", {"part": "contentDetails,status,statistics,snippet",
                                    "id": ",".join(chunk)})
        except Exception as e:
            print(f"  [api error] videos.list: {e}")
            return None  # signal failure -> caller skips pruning
        for it in data.get("items", []):
            st = it.get("status", {}); cd = it.get("contentDetails", {})
            sn = it.get("snippet", {}); stt = it.get("statistics", {})
            out[it["id"]] = {
                "dur": parse_duration(cd.get("duration")),
                "embeddable": st.get("embeddable", False),
                "public": st.get("privacyStatus") == "public",
                "processed": st.get("uploadStatus", "processed") == "processed",
                "views": int(stt.get("viewCount", 0) or 0),
                "live": sn.get("liveBroadcastContent", "none") != "none",
            }
    return out


def prune(channels):
    """Drop single-video channels the API says are bad. Returns (kept, dropped)."""
    singles = {}
    for c in channels:
        if c.get("cat") in NO_PRUNE_CATS:
            continue
        vid = _vid_id(c.get("embed", ""))
        if vid:
            singles[vid] = c
    if not singles:
        return channels, []
    meta = fetch_video_meta(list(singles.keys()))
    if meta is None:
        print("  [prune] skipped (API unavailable)")
        return channels, []
    dropped = []
    for vid, c in singles.items():
        m = meta.get(vid)
        bad = None
        if m is None:
            bad = "removed/unavailable"
        elif m["live"]:
            bad = None  # live stream: keep, don't judge duration
        elif not m["embeddable"]:
            bad = "embedding disabled"
        elif not m["public"]:
            bad = "not public"
        elif m["dur"] and m["dur"] < MIN_SECONDS:
            bad = f"too short ({m['dur']}s)"
        elif m["views"] < MIN_VIEWS:
            bad = f"low views ({m['views']})"
        if bad:
            dropped.append((c.get("id"), bad))
    drop_ids = {d[0] for d in dropped}
    kept = [c for c in channels if c.get("id") not in drop_ids]
    return kept, dropped


def grow(channels):
    """Search on-theme queries and append new, validated channels."""
    if len(channels) >= TARGET_MAX:
        return channels, []
    have = set()
    for c in channels:
        v = _vid_id(c.get("embed", ""))
        if v:
            have.add(v)
    added = []
    budget = min(MAX_ADD, TARGET_MAX - len(channels))
    for query, cat, prefix in GROW_QUERIES:
        if len(added) >= budget:
            break
        try:
            res = _api("search", {"part": "snippet", "q": query, "type": "video",
                                  "videoDuration": "long", "videoEmbeddable": "true",
                                  "videoSyndicated": "true", "order": "viewCount",
                                  "maxResults": 6})
        except Exception as e:
            print(f"  [api error] search '{query}': {e}")
            continue
        cand_ids = [it["id"]["videoId"] for it in res.get("items", [])
                    if it.get("id", {}).get("videoId") and it["id"]["videoId"] not in have]
        if not cand_ids:
            continue
        meta = fetch_video_meta(cand_ids)
        if not meta:
            continue
        for vid in cand_ids:
            m = meta.get(vid)
            if not m or m["live"]:
                continue
            if (m["embeddable"] and m["public"] and m["dur"] >= max(MIN_SECONDS, 1200)
                    and m["views"] >= MIN_VIEWS):
                # title for label
                title = next((it["snippet"]["title"] for it in res["items"]
                              if it["id"].get("videoId") == vid), "Live Set")
                title = re.sub(r"\s+", " ", title).strip()[:48]
                added.append({
                    "id": "auto-" + vid,
                    "cat": cat,
                    "maxIdx": 1,
                    "label": f"{prefix} {title}",
                    "embed": "https://www.youtube.com/embed/" + vid,
                    "origin": "auto",
                    "added": int(time.time()),
                })
                have.add(vid)
                break  # one per query per run
    return channels + added, added


def main():
    if not API_KEY:
        print("[curate] YOUTUBE_API_KEY not set — skipping (channels.json unchanged).")
        return
    try:
        with open(CHAN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        channels = data.get("channels") if isinstance(data, dict) else data
        assert isinstance(channels, list) and len(channels) >= MIN_TOTAL
    except Exception as e:
        print(f"[curate] can't read {CHAN_FILE} ({e}) — aborting.")
        return
    original = len(channels)
    print(f"[curate] start: {original} channels")

    kept, dropped = prune(channels)
    for cid, why in dropped:
        print(f"  - pruned {cid}: {why}")
    print(f"[curate] pruned {len(dropped)} -> {len(kept)} channels")

    grown, added = grow(kept)
    for c in added:
        print(f"  + added {c['id']} [{c['cat']}]")
    print(f"[curate] added {len(added)} -> {len(grown)} channels")

    # de-dupe by id, keep order
    seen, final = set(), []
    for c in grown:
        if c.get("id") and c["id"] not in seen:
            seen.add(c["id"]); final.append(c)

    # sanity gate
    if len(final) < max(MIN_TOTAL, int(original * 0.8)):
        print(f"[curate] sanity gate hit ({len(final)} < floor) — NOT writing.")
        return
    try:
        with open(CHAN_FILE + ".bak", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(CHAN_FILE, "w", encoding="utf-8") as f:
            json.dump({"updated": int(time.time()), "count": len(final),
                       "channels": final}, f, ensure_ascii=False, indent=2)
        print(f"[curate] wrote {CHAN_FILE}: {original} -> {len(final)} channels")
    except Exception as e:
        print(f"[curate] write failed: {e}")


if __name__ == "__main__":
    main()
