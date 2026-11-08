#!/usr/bin/env python3
"""
Party Portal — Channel Curation Agent 3.0
=========================================
Runs in the GitHub Action after bot.py and keeps channels.json healthy.

WITHOUT any API key (always):
  1. CHECK   every channel: single videos via YouTube oEmbed (fast: 401 = embedding
             disabled, 403/404 = private or removed); live cams and 24/7 radio also via
             the public watch page (is it actually live right now?); playlists via their
             playlist page; inline video lists video by video.
  2. PRUNE   definitively dead entries at once; a live stream that is merely offline gets
             a strike and is dropped after 2 runs in a row (so a cam rebooting overnight
             is not lost).
  3. REFILL  the Live World Cams lane from official cam operators (YouTube's own search
             page, live filter) when it falls below its floor, so the wall never runs out
             of party cams.
WITH a YOUTUBE_API_KEY secret (optional): the 2.x API growth path also runs, limited to
official channels.

SAFETY: never writes if a run would drop more than MAX_DROP_SHARE of the catalogue or
leave fewer than MIN_TOTAL (a YouTube / network hiccup cannot empty the wall); every
network step has a time budget; anything unclear counts as "keep". index.html validates
channels.json and falls back to its built-in list if anything is off.
Standard library only.
"""
import json, os, re, sys, time, threading
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API_KEY        = os.environ.get("YOUTUBE_API_KEY", "").strip()
CHAN_FILE      = "channels.json"
MIN_TOTAL      = 120          # never let the catalogue fall below this
MAX_DROP_SHARE = 0.15         # a run that would drop more than this is treated as a glitch
LIVE_STRIKES   = 2            # offline runs in a row before a live channel is dropped
CAM_FLOOR      = 55           # refill Live World Cams below this
CAM_REFILL_MAX = 8            # new cams per run
BUDGET_OEMBED  = 240          # seconds
BUDGET_WATCH   = 200          # seconds (live checks)
BUDGET_REFILL  = 90           # seconds
LIVE_CATS      = {"LIVE CAM", "RADIO"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Cookie": "CONSENT=YES+1; SOCS=CAI"}

_lock = threading.Lock()
_last = [0.0]
_429 = [0]


def _open(req, timeout=15, gap=0.25):
    """Throttled urlopen shared by every thread; counts 429 answers."""
    with _lock:
        wait = _last[0] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            _429[0] += 1
        raise


def oembed(vid):
    """'ok' | 'dead' | 'unknown' for one video id."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote("https://www.youtube.com/watch?v=" + vid, safe="")
    try:
        with _open(urllib.request.Request(url, headers={"User-Agent": UA}), gap=0.12) as r:
            json.loads(r.read())
            return "ok"
    except urllib.error.HTTPError as e:
        return "dead" if e.code in (401, 403, 404) else "unknown"
    except Exception:
        return "unknown"


_PR = re.compile(r"var ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*(?:var |</script>)", re.S)
_DEAD = re.compile(r"unavailable|not available|private|removed|terminated|no longer|has ended|does not exist|deleted", re.I)
_AGE = re.compile(r"confirm your age|age-restricted|inappropriate for some users", re.I)
_BOT = re.compile(r"not a bot|unusual traffic", re.I)


def watch_state(vid):
    """For live channels: 'live' | 'offline' | 'dead' | 'unknown' (public watch page)."""
    try:
        with _open(urllib.request.Request("https://www.youtube.com/watch?v=" + vid + "&hl=en", headers=H), gap=0.6) as r:
            page = r.read().decode("utf-8", "ignore")
    except Exception:
        return "unknown"
    m = _PR.search(page)
    if not m:
        return "unknown"
    try:
        pr = json.loads(m.group(1))
    except Exception:
        return "unknown"
    ps, vd = pr.get("playabilityStatus") or {}, pr.get("videoDetails") or {}
    st, reason = str(ps.get("status", "")), str(ps.get("reason", "") or "")
    if st == "OK":
        if ps.get("playableInEmbed") is False:
            return "dead"
        return "live" if vd.get("isLive") else "offline"
    if st == "LOGIN_REQUIRED":
        if _AGE.search(reason):
            return "dead"
        return "dead" if "private" in reason.lower() else "unknown"
    if st == "LIVE_STREAM_OFFLINE":
        return "offline"
    if st in ("ERROR", "UNPLAYABLE"):
        if _AGE.search(reason):
            return "dead"
        return "dead" if (_DEAD.search(reason) or not reason) else "unknown"
    return "unknown"


def playlist_state(list_id):
    try:
        with _open(urllib.request.Request("https://www.youtube.com/playlist?list=" + list_id + "&hl=en", headers=H), gap=0.6) as r:
            page = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return "dead" if e.code in (404, 410) else "unknown"
    except Exception:
        return "unknown"
    if re.search(r'"alertRenderer".{0,400}(does not exist|is private|unavailable)', page, re.S):
        return "dead"
    return "ok" if re.search(r'"(contentId|videoId)":"[A-Za-z0-9_-]{11}"', page) else "unknown"


def parts(c):
    if isinstance(c.get("items"), list) and c["items"]:
        return "ids", [it.get("v") for it in c["items"] if it.get("v")]
    e = c.get("embed", "")
    lst = re.search(r"[?&]list=([A-Za-z0-9_-]+)", e)
    ids = re.search(r"[?&]playlist=([A-Za-z0-9_,-]+)", e)
    vid = re.search(r"/embed/([A-Za-z0-9_-]{11})", e)
    if ids and vid:
        return "ids", [vid.group(1)] + [x for x in ids.group(1).split(",") if x]
    if lst:
        return "list", lst.group(1)
    if vid:
        return "vid", vid.group(1)
    return "?", None


def is_live_entry(c):
    return bool(c.get("live")) or c.get("cat") in LIVE_CATS


# ───────────────────────── no-key refill: Live World Cams ─────────────────────────
CTX = {"client": {"clientName": "WEB", "clientVersion": "2.20261105.09.00", "hl": "en", "gl": "US"}}
CAM_OPERATORS = re.compile(r"(earthcam|skylinewebcams|ptztv|ozolio|wwltv|fox 5|annnewsch|fnn|elbo room|seek key west|"
                           r"seek florida keys|world live cams|webcams de m[eé]xico|homes in rio|the real samui webcam|"
                           r"caribbean webcams|showme caribbean|beach tv|webcamsydney|teleport\.camera|"
                           r"hogs breath|sloppyjoes|myrtle beach|ae signage|tbs news|abema|explore)", re.I)
CAM_PLACES = re.compile(r"(vegas|fremont|times square|bourbon|new orleans|french quarter|duval|key west|miami|south beach|"
                        r"ocean drive|ibiza|mykonos|canc[uú]n|playa del carmen|tulum|copacabana|ipanema|rio de janeiro|shibuya|"
                        r"kabukicho|dotonbori|waikiki|venice beach|santa monica|fort lauderdale|panama city|daytona|"
                        r"south padre|nashville|broadway|temple bar|amsterdam|tenerife|benidorm|bondi|surfers paradise|"
                        r"abbey road|patong|bangla|khao san|phuket|koh phangan|cabo|myrtle beach|boardwalk|beach bar|beach club)", re.I)
CAM_JUNK = re.compile(r"(ambien|sounds|relaxing|bossa|jazz|lounge|chillout|virtual tour|walking|\bwalk|\btour\b|pre-recorded|"
                      r"episodes|cruise ship|\bmix\b|music|lofi|bgm|asmr|study|sleep|timelapse|replay|recorded|traffic|weather)", re.I)
CAM_QUERIES = ["las vegas strip live cam", "fremont street live cam", "times square live cam", "bourbon street live cam",
               "duval street live cam", "miami beach live cam", "ibiza live webcam", "copacabana live cam",
               "shibuya crossing live camera", "kabukicho live camera", "dotonbori live camera", "waikiki live cam",
               "venice beach live cam", "fort lauderdale beach live cam", "panama city beach live cam", "cancun live cam",
               "nashville broadway live cam", "patong beach live cam", "mykonos live cam", "playa del carmen live cam"]


def _walk(o, out):
    if isinstance(o, dict):
        if "videoRenderer" in o:
            v = o["videoRenderer"]
            runs = (v.get("ownerText") or {}).get("runs") or [{}]
            live = any("LIVE" in ((b.get("metadataBadgeRenderer") or {}).get("style") or "") for b in v.get("badges", []))
            out.append({"vid": v.get("videoId"), "title": "".join(r.get("text", "") for r in (v.get("title") or {}).get("runs", [])),
                        "owner": "".join(r.get("text", "") for r in runs), "live": live})
            return
        for x in o.values():
            _walk(x, out)
    elif isinstance(o, list):
        for x in o:
            _walk(x, out)


def yt_search_live(query):
    body = {"context": CTX, "query": query, "params": "EgJAAQ=="}
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
                                 data=json.dumps(body).encode(), headers=dict(H, **{"Content-Type": "application/json"}))
    with _open(req, gap=0.8) as r:
        d = json.loads(r.read())
    out = []
    _walk(d, out)
    return [x for x in out if x.get("vid") and x.get("live")]


def cam_label(title):
    t = re.sub("[\U0001F000-\U0001FAFF☀-➿️]+", " ", title or "")
    t = re.sub(r"\b(earthcam live|live cam|live webcam|webcam|live camera|live stream|livestream|live|cam|24/7|4k|hd)\b", " ", t, flags=re.I)
    t = re.sub(r"[\[\]【】()|:]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -—,")
    if len(t) > 58:
        t = t[:58].rsplit(" ", 1)[0] + "…"
    return "\U0001F4E1 " + (t or "Live World Cam")


def refill_cams(channels, deadline):
    cams = [c for c in channels if c.get("cat") == "LIVE CAM"]
    if len(cams) >= CAM_FLOOR:
        return []
    have = {parts(c)[1] for c in channels if parts(c)[0] == "vid"}
    added = []
    for q in CAM_QUERIES:
        if time.time() > deadline or len(added) >= CAM_REFILL_MAX or len(cams) + len(added) >= CAM_FLOOR + 5:
            break
        try:
            res = yt_search_live(q)
        except Exception as e:
            print(f"  [refill] search '{q}': {e}")
            continue
        for r in res:
            t, o = r["title"], r["owner"]
            if r["vid"] in have or CAM_JUNK.search(t + " " + o):
                continue
            if not (CAM_OPERATORS.search(o) and CAM_PLACES.search(t)):
                continue
            if oembed(r["vid"]) != "ok":
                continue
            have.add(r["vid"])
            added.append({"id": "livecam-" + r["vid"], "cat": "LIVE CAM", "maxIdx": 1, "label": cam_label(t),
                          "embed": "https://www.youtube.com/embed/" + r["vid"], "src": o, "live": True,
                          "origin": "refill-" + time.strftime("%Y-%m-%d")})
            break        # one per query per run
    return added


# ───────────────────────── optional: YouTube Data API growth ─────────────────────────
OFFICIAL_CHANNELS = re.compile(r"^(cercle|tomorrowland|ultra music festival|umf tv|insomniac|boiler room|mixmag|dj mag|"
                               r"hör berlin|defected records|anjunadeep|above & beyond|kexp|arte concert|rolling loud|"
                               r"npr music|sports illustrated swimsuit|fashiontv|art hearts fashion|fashionstock|q-dance|"
                               r"ukf drum & bass|live aid|mtv|mtv vault|earthcam)$", re.I)
GROW_QUERIES = [("Cercle live set", "CERCLE"), ("Tomorrowland full set", "FESTIVAL"), ("Ultra Music Festival full set", "FESTIVAL"),
                ("Boiler Room full set", "CLUB"), ("Mixmag the lab full set", "CLUB"), ("Rolling Loud full set", "HIPHOP"),
                ("KEXP full performance", "ROCK"), ("ARTE Concert Hellfest", "ROCK"), ("Miami Swim Week runway", "SWIM"),
                ("Anjunadeep open air full set", "ANJUNA")]


def _api(endpoint, params):
    params["key"] = API_KEY
    url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def api_grow(channels, max_add=12):
    have = {parts(c)[1] for c in channels if parts(c)[0] == "vid"}
    added = []
    for q, cat in GROW_QUERIES:
        if len(added) >= max_add:
            break
        try:
            res = _api("search", {"part": "snippet", "q": q, "type": "video", "videoDuration": "long",
                                  "videoEmbeddable": "true", "videoSyndicated": "true", "order": "viewCount", "maxResults": 8})
        except Exception as e:
            print(f"  [api] search '{q}': {e}")
            continue
        for it in res.get("items", []):
            vid = (it.get("id") or {}).get("videoId")
            sn = it.get("snippet") or {}
            if not vid or vid in have or not OFFICIAL_CHANNELS.search((sn.get("channelTitle") or "").strip()):
                continue
            title = re.sub(r"\s+", " ", sn.get("title", "")).strip()[:60]
            added.append({"id": cat.lower().replace(" ", "") + "-" + vid, "cat": cat, "maxIdx": 1, "label": "✨ " + title,
                          "embed": "https://www.youtube.com/embed/" + vid, "src": sn.get("channelTitle", ""),
                          "origin": "api-" + time.strftime("%Y-%m-%d")})
            have.add(vid)
            break
    return added


def write_channels(channels, stats):
    body = ",\n".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in channels)
    txt = ('{"updated":%d,"count":%d,"checked":%s,"channels":[\n%s\n]}\n'
           % (int(time.time()), len(channels), json.dumps(stats, separators=(",", ":")), body))
    tmp = CHAN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(txt)
    os.replace(tmp, CHAN_FILE)


def main():
    t0 = time.time()
    try:
        with open(CHAN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        channels = data.get("channels") if isinstance(data, dict) else data
        assert isinstance(channels, list) and len(channels) >= MIN_TOTAL
    except Exception as e:
        print(f"[curate] can't read {CHAN_FILE} ({e}) — nothing changed.")
        return
    original = len(channels)
    print(f"[curate 3.0] start: {original} channels")

    # 1) oEmbed every single video and every id of inline lists
    vids = []
    for c in channels:
        k, v = parts(c)
        if k == "vid":
            vids.append(v)
        elif k == "ids":
            vids.extend(v)
    vids = list(dict.fromkeys(vids))
    oe = {}
    deadline = t0 + BUDGET_OEMBED

    def chk(v):
        if time.time() > deadline or _429[0] > 25:
            return v, "unknown"
        return v, oembed(v)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for v, st in ex.map(chk, vids):
            oe[v] = st
    # 2) live channels: are they live right now?
    live_vids = [parts(c)[1] for c in channels if is_live_entry(c) and parts(c)[0] == "vid" and oe.get(parts(c)[1]) != "dead"]
    ws = {}
    wdeadline = time.time() + BUDGET_WATCH

    def wchk(v):
        if time.time() > wdeadline or _429[0] > 25:
            return v, "unknown"
        return v, watch_state(v)
    with ThreadPoolExecutor(max_workers=3) as ex:
        for v, st in ex.map(wchk, live_vids):
            ws[v] = st
    # 3) playlists
    ps = {}
    for c in channels:
        k, v = parts(c)
        if k == "list" and time.time() < wdeadline + 60 and _429[0] <= 25:
            ps[v] = playlist_state(v)

    kept, dropped = [], []
    for c in channels:
        k, v = parts(c)
        why = None
        if k == "vid":
            if oe.get(v) == "dead":
                why = "removed / private / embedding disabled"
            elif is_live_entry(c):
                st = ws.get(v, "unknown")
                if st == "dead":
                    why = "live stream gone"
                elif st == "offline":
                    c["strikes"] = int(c.get("strikes", 0)) + 1
                    if c["strikes"] >= LIVE_STRIKES:
                        why = "not live for %d runs" % c["strikes"]
                elif st == "live":
                    c.pop("strikes", None)
        elif k == "ids":
            alive = [x for x in v if oe.get(x) != "dead"]
            if c.get("items"):
                # playlist channel: drop just the dead videos, keep the channel while any remain
                if not alive:
                    why = "playlist channel: every video gone"
                elif len(alive) < len(v):
                    c["items"] = [it for it in c["items"] if it.get("v") in alive]
                    c["embed"] = ("https://www.youtube.com/embed/" + alive[0]
                                  + (("?playlist=" + ",".join(alive[1:]) + "&loop=1") if len(alive) > 1 else ""))
                    print(f"  ~ {c.get('id')}: removed {len(v) - len(alive)} dead video(s)")
            elif len(alive) < 3:
                why = "inline list: only %d videos left" % len(alive)
            elif len(alive) < len(v):
                c["embed"] = "https://www.youtube.com/embed/" + alive[0] + "?playlist=" + ",".join(alive[1:]) + "&loop=1"
        elif k == "list":
            if ps.get(v) == "dead":
                c["strikes"] = int(c.get("strikes", 0)) + 1
                if c["strikes"] >= LIVE_STRIKES:
                    why = "playlist gone"
            elif ps.get(v) == "ok":
                c.pop("strikes", None)
        if why:
            dropped.append((c.get("id"), why))
        else:
            kept.append(c)
    for cid, why in dropped:
        print(f"  - drop {cid}: {why}")

    # 4) refill Live World Cams (no key) + optional API growth
    added = []
    try:
        added += refill_cams(kept, time.time() + BUDGET_REFILL)
    except Exception as e:
        print(f"  [refill] skipped: {e}")
    if API_KEY:
        try:
            added += api_grow(kept + added)
        except Exception as e:
            print(f"  [api] skipped: {e}")
    for c in added:
        print(f"  + add {c['id']} [{c['cat']}] {c['label']}")

    seen, final = set(), []
    for c in kept + added:
        if c.get("id") and c["id"] not in seen:
            seen.add(c["id"])
            final.append(c)
    unknown = sum(1 for s in list(oe.values()) + list(ws.values()) if s == "unknown")
    stats = {"at": int(time.time()), "oembed": len(oe), "live_checked": len(ws), "unknown": unknown,
             "dropped": len(dropped), "added": len(added), "http429": _429[0], "secs": int(time.time() - t0)}
    print(f"[curate] checked {len(oe)} videos + {len(ws)} live + {len(ps)} playlists in {stats['secs']}s; "
          f"unknown {unknown}; 429s {_429[0]}; drop {len(dropped)}; add {len(added)}")
    if len(dropped) > max(3, int(original * MAX_DROP_SHARE)) or len(final) < MIN_TOTAL:
        print(f"[curate] sanity gate: {len(dropped)} drops of {original} looks like a glitch — NOT writing.")
        return
    write_channels(final, stats)
    print(f"[curate] wrote {CHAN_FILE}: {original} -> {len(final)} channels")


if __name__ == "__main__":
    main()
