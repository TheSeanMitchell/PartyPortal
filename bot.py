#!/usr/bin/env python3
"""
PARTY PORTAL — Content Bot  (real news only)
=============================================
Aggregates *real* party / festival / nightlife / EDM headlines from Google
News RSS, then cleans, filters and de-duplicates them into feed.json.

Key quality techniques (borrowed from the NUZU aggregator):
  • site:<domain> queries pull straight from trusted music/nightlife press
  • trailing " - Source Name" stripped from every display title
  • junk/spam filter drops tracking-code titles, daily-digest pages, etc.
  • source-trust tiers (1=specialist/major, 2=solid, 3=other) drive the dot colour
  • broad outlets (Billboard, Pitchfork…) must match a party keyword;
    specialist EDM outlets are accepted on-topic by default
  • NO synthetic / placeholder items are ever written — if nothing real
    passes the filters, feed.json is left untouched.

The bot writes feed.json ONLY. It never edits index.html (the page fetches
feed.json at runtime). Runs on GitHub Actions 3×/day.

Run locally:  python bot.py    (Python 3.8+, standard library only)
"""

import os, re, json, time, hashlib, html as htmllib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET
import urllib.request, urllib.error

# ───────────────────────────── CONFIG ─────────────────────────────
MAX_ITEMS      = 55
BREAKING_HOURS = 36     # < 36h old  → "hot"
DAILY_HOURS    = 48     # < 48h old  → kept (today + yesterday)
FETCH_TIMEOUT  = 12
MAX_WORKERS    = 12
MIN_TITLE_LEN  = 28
MAX_TITLE_LEN  = 200

# ──────────────────────── PARTY-CULTURE KEYWORDS ───────────────────
RAW_KEYWORDS = [
    # festivals / scene
    "festival","festival lineup","festival headliner","festival announcement",
    "festival tickets","music festival","edm festival","dance music festival",
    "electronic music festival","festival season","festival stage","mainstage",
    "coachella","edc","electric daisy carnival","ultra music festival","ultra miami",
    "tomorrowland","glastonbury","lollapalooza","bonnaroo","burning man","black rock city",
    "creamfields","lost lands","awakenings","lucidity","day trip","ushuaia","ushuaïa",
    "dc10","amnesia ibiza","hi ibiza","pacha ibiza","iii points","movement detroit",
    "electric forest","electric zoo","edc orlando","nocturnal wonderland","hard summer",
    "sxsw","south by southwest","outside lands","governors ball","mysteryland","defqon",
    "tomorrowland winter","tomorrowland brasil","afterlife festival","time warp",
    # electronic music / djs
    "edm","dj set","dj residency","dj tour","techno","house music","trance","dubstep",
    "bass music","hardstyle","drum and bass","rave","rave culture","underground rave",
    "boiler room","beatport","resident advisor","electronic dance music","b2b set",
    "tiesto","martin garrix","david guetta","calvin harris","deadmau5","skrillex","diplo",
    "marshmello","afrojack","armin van buuren","eric prydz","bicep","four tet","fred again",
    "charlotte de witte","amelie lens","peggy gou","john summit","disclosure","chris lake",
    # nightlife / venues
    "nightlife","nightclub","club night","club culture","club opening","rooftop party",
    "vegas nightlife","las vegas nightclub","vegas residency","las vegas sphere","sphere las vegas",
    "bourbon street","new orleans nightlife","mardi gras","key west","ibiza party","ibiza season",
    "miami nightlife","miami beach party","art basel miami","berlin techno","berlin club",
    "amsterdam club","london club","warehouse party","after hours","day party","pool party",
    # culture / live music adjacents
    "concert tour","tour dates","summer concerts","amphitheater","live show","residency",
    "festival fashion","coachella fashion","rave outfit","festival outfit","festival style",
    "mtv spring break","spring break",
]
KEYWORDS = set(k.lower() for k in RAW_KEYWORDS)

def make_pattern(words):
    esc = [re.escape(w) for w in sorted(words, key=len, reverse=True)]
    return re.compile(r'\b(?:' + '|'.join(esc) + r')\b', re.IGNORECASE) if esc else None

KEYWORD_PAT = make_pattern(KEYWORDS)

# keep the feed party-positive (drop hard news / negativity)
BLOCKLIST = {
    "war","bombing","missile","airstrike","massacre","genocide","terrorist","terror attack",
    "shooting","stabbing","murder","killed","dead","death toll","manslaughter","overdose death",
    "arrest","arrested","lawsuit","sues","indicted","conviction","convicted","prison","sentenced",
    "rape","assault charges","sexual assault","harassment lawsuit","abuse allegations","trafficking",
    "inflation","recession","stock market","fed rate","federal reserve","layoffs","bankruptcy",
    "immigration","border","deportation","politics","election","republican","democrat","congress",
    "senate","white house","supreme court","foreign policy","nato","ukraine","gaza","israel",
    "palestine","iran","obituary","dies at","has died","passes away","funeral","memorial",
    "drugs","drug bust","police raid","raids","seized","narcotics","crackdown","banned",
    "steam launch","gacha","anime","esports","video game","crypto","nft",
}
BLOCK_PAT = make_pattern(BLOCKLIST)

# ───────────────────── SOURCE TRUST + FRIENDLY NAMES ───────────────
TIER1 = {  # specialist EDM/dance press + major outlets
    "mixmag","dj mag","djmag","resident advisor","ra","edm.com","dancing astronaut",
    "billboard","rolling stone","pitchfork","nme","variety","stereogum","consequence",
    "the guardian","bbc","npr","associated press","ap news","reuters","time out",
}
TIER2 = {  # solid music/culture blogs & city press
    "edmtunes","your edm","we rave you","6am","magnetic magazine","magnetic mag",
    "electronic groove","edm identity","dancing astronaut","festicket","ticketnews",
    "vegas weekly","las vegas review-journal","timeout","attack magazine","mixdown",
    "the line of best fit","clash","diy magazine","brooklyn vegan","spin","paper magazine",
}
NICHE_SOURCES = {  # accepted on-topic even without a generic keyword hit
    "mixmag","dj mag","djmag","resident advisor","edm.com","dancing astronaut","edmtunes",
    "your edm","we rave you","6am","magnetic magazine","magnetic mag","electronic groove",
    "edm identity","attack magazine","ra",
}

def _name_has(n, s):
    # short codes (<=3 chars, e.g. "ra") must match a whole word, not a substring
    if len(s) <= 3:
        return s in n.split()
    return s in n

def source_tier(name):
    n = (name or "").lower()
    if any(_name_has(n, s) for s in TIER1): return 1
    if any(_name_has(n, s) for s in TIER2): return 2
    return 3

def is_niche(name):
    n = (name or "").lower()
    return any(_name_has(n, s) for s in NICHE_SOURCES)

# ─────────────────────────── RSS SOURCES ───────────────────────────
def g(q):
    return "https://news.google.com/rss/search?q=" + q + "&hl=en-US&gl=US&ceid=US:en"

CULTURE_SOURCES = [
    # specialist EDM / dance press via site: queries (clean + on-topic)
    ("Mixmag",            g("site:mixmag.net+when:3d")),
    ("DJ Mag",            g("site:djmag.com+when:3d")),
    ("Resident Advisor",  g("site:ra.co+when:3d")),
    ("EDM.com",           g("site:edm.com+when:3d")),
    ("Dancing Astronaut", g("site:dancingastronaut.com+when:3d")),
    ("Your EDM",          g("site:youredm.com+when:3d")),
    ("EDMTunes",          g("site:edmtunes.com+when:3d")),
    ("We Rave You",       g("site:weraveyou.com+when:3d")),
    ("Electronic Groove", g("site:electronicgroove.com+when:4d")),
    ("Magnetic Magazine", g("site:magneticmag.com+when:4d")),
    ("6AM",               g("site:6amgroup.com+when:4d")),
    # festival-specific (broad search, will be keyword-filtered)
    ("Festivals",         g("music+festival+2026+OR+festival+lineup+OR+festival+headliner+when:2d")),
    ("EDC / EDM Fests",   g("electric+daisy+carnival+OR+EDC+OR+ultra+music+festival+OR+tomorrowland+when:3d")),
    ("Coachella",         g("coachella+festival+OR+coachella+lineup+when:3d")),
    ("Lollapalooza",      g("lollapalooza+2026+OR+lollapalooza+lineup+when:3d")),
    ("Creamfields",       g("creamfields+festival+OR+creamfields+2026+when:3d")),
    ("Burning Man",       g("burning+man+2026+OR+black+rock+city+when:4d")),
    ("Rave / Techno",     g("rave+OR+techno+festival+OR+warehouse+party+OR+boiler+room+when:2d")),
    # nightlife / cities
    ("Nightlife",         g("nightlife+OR+nightclub+OR+club+night+when:2d")),
    ("Ibiza",             g("ibiza+club+OR+ibiza+season+OR+ushuaia+ibiza+when:3d")),
    ("Vegas Party",       g("las+vegas+nightlife+OR+vegas+nightclub+OR+las+vegas+sphere+when:2d")),
    ("New Orleans",       g("bourbon+street+OR+new+orleans+nightlife+OR+mardi+gras+when:3d")),
    ("Miami",             g("miami+nightlife+OR+miami+beach+party+OR+art+basel+miami+when:3d")),
    # broad music press (site: → high quality; keyword-filtered for relevance)
    ("Billboard Dance",   g("site:billboard.com+dance+OR+electronic+OR+festival+when:2d")),
    ("Rolling Stone",     g("site:rollingstone.com+festival+OR+electronic+OR+dj+when:2d")),
    ("Pitchfork",         g("site:pitchfork.com+festival+OR+electronic+when:3d")),
    ("NME",               g("site:nme.com+festival+OR+dance+when:3d")),
    ("DJ Tours",          g("dj+residency+OR+dj+tour+2026+OR+b2b+set+when:2d")),
    ("Festival Fashion",  g("coachella+fashion+OR+festival+outfit+OR+rave+outfit+when:3d")),
]

# ───────────────────────── FETCH + PARSE ───────────────────────────
def _fetch_rss(name, url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PartyPortalBot/2.0)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        out = []
        for item in root.iter("item"):
            t_el = item.find("title")
            l_el = item.find("link")
            p_el = item.find("pubDate")
            s_el = item.find("{https://news.google.com/rss}source") or item.find("source")
            if t_el is None or not t_el.text:
                continue
            title = htmllib.unescape(t_el.text.strip())
            link  = (l_el.text or "").strip() if l_el is not None else ""
            src   = s_el.text.strip() if (s_el is not None and s_el.text) else name
            domain = ""
            if s_el is not None:
                surl = s_el.get("url") or ""
                m = re.search(r"https?://([^/]+)", surl)
                if m:
                    domain = m.group(1).lower().replace("www.", "")
            ts = 0
            if p_el is not None and p_el.text:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                            "%a, %d %b %Y %H:%M:%S +0000"):
                    try:
                        dt = datetime.strptime(p_el.text.strip(), fmt)
                        ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt.tzinfo is None else int(dt.timestamp())
                        break
                    except ValueError:
                        pass
            if not ts:
                ts = int(time.time()) - 3600
            out.append((ts, title, link, src, domain))
        return out
    except Exception as e:
        print(f"  [WARN] {name}: {e}")
        return []

def fetch_all():
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_rss, n, u): n for n, u in CULTURE_SOURCES}
        for f in as_completed(futures):
            results.extend(f.result())
    return results

# ──────────────────── CLEANING / JUNK DETECTION ────────────────────
def strip_source(title):
    """Remove a trailing ' - Source Name' (<=5 words) appended by Google News."""
    if " - " not in title:
        return title
    head, tail = title.rsplit(" - ", 1)
    if len(tail.split()) <= 5:
        return head.strip()
    return title

_TRACKING_RE = re.compile(r"\(([A-Za-z0-9]{6,16})\)")
_JUNK_PHRASES = (
    "print edition", "today's paper", "todays paper", "daily digest",
    "daily briefing", "front page", "newspaper - magzter", "- magzter",
    "week in review |", "watch live:", "live updates:",
)

def is_junk(title):
    tl = title.lower()
    # tracking-code titles (two Google headlines mashed together / spam)
    for m in _TRACKING_RE.findall(title):
        if any(c.isdigit() for c in m) and any(c.isalpha() for c in m) and m != m.lower() and m != m.upper():
            return True
    for p in _JUNK_PHRASES:
        if p in tl:
            return True
    # absurdly long mashups
    if len(title.split()) > 28:
        return True
    return False

def categorize(title):
    t = title.lower()
    if any(w in t for w in ["festival","lineup","headliner","coachella","edc","tomorrowland",
                            "ultra","glastonbury","lollapalooza","bonnaroo","burning man",
                            "creamfields","lost lands","awakenings","iii points","outside lands"]):
        return "Festival"
    if any(w in t for w in ["nightclub","club night","nightlife","rave","ibiza","sphere",
                            "warehouse","after hours","bourbon street","mardi gras"]):
        return "Nightlife"
    if any(w in t for w in ["dj","edm","electronic","techno","house music","dance music",
                            "boiler room","trance","dubstep","hardstyle","drum and bass"]):
        return "EDM"
    if any(w in t for w in ["fashion","outfit","style","runway","looks"]):
        return "Fashion"
    if any(w in t for w in ["concert","tour","live show","residency","ticket","amphitheater"]):
        return "Concert"
    return "Culture"

def time_label(age_sec):
    if age_sec < 3600:   return f"{max(1, age_sec // 60)} min ago"
    if age_sec < 86400:  return f"{age_sec // 3600} hr ago"
    if age_sec < 172800: return "1 day ago"
    return f"{age_sec // 86400} days ago"

def _key(title):
    t = re.sub(r"[^a-z0-9 ]", "", strip_source(title).lower())
    return " ".join(t.split()[:12])

_STOP = set(("the a an and or of to in for on at with from your you their his her its this that "
             "these those is are was were be been being new live full set mix official video as "
             "2026 2025 2024 ft feat vs after first time bring back into out over more most").split())

def _sigwords(title):
    t = re.sub(r"[^a-z0-9 ]", " ", strip_source(title).lower())
    return set(w for w in t.split() if len(w) > 3 and w not in _STOP)

_DOMAIN_MAP = {
    "mixmag": "mixmag.net", "dj mag": "djmag.com", "djmag": "djmag.com",
    "resident advisor": "ra.co", "ra": "ra.co", "edm.com": "edm.com",
    "edm": "edm.com", "dancing astronaut": "dancingastronaut.com",
    "your edm": "youredm.com", "edmtunes": "edmtunes.com", "we rave you": "weraveyou.com",
    "weraveyou": "weraveyou.com", "edm identity": "edmidentity.com",
    "billboard": "billboard.com", "rolling stone": "rollingstone.com",
    "pitchfork": "pitchfork.com", "stereogum": "stereogum.com", "nme": "nme.com",
    "consequence": "consequence.net", "variety": "variety.com", "the guardian": "theguardian.com",
    "spin": "spin.com", "loudwire": "loudwire.com", "ultimate classic rock": "ultimateclassicrock.com",
    "kerrang": "kerrang.com", "magnetic magazine": "magneticmag.com", "6am": "6amgroup.com",
    "djs from mars": "djmag.com", "the nocturnal times": "thenocturnaltimes.com",
    "edm sauce": "edmsauce.com", "data transmission": "datatransmission.co",
    "attack magazine": "attackmagazine.com", "mixmag asia": "mixmag.asia",
    "the dj list": "thedjlist.com", "ravejungle": "ravejungle.com", "decoded magazine": "decodedmagazine.com",
}
def _guess_domain(src):
    if not src:
        return ""
    return _DOMAIN_MAP.get(src.strip().lower(), "")

def build_item(ts, title, link, src, domain=""):
    """Apply all cleaning/filters. Return dict or None if rejected."""
    if len(title) < MIN_TITLE_LEN or len(title) > MAX_TITLE_LEN:
        return None
    if is_junk(title):
        return None
    if BLOCK_PAT and BLOCK_PAT.search(title):
        return None
    # relevance: specialist EDM sources accepted on-topic; everything else
    # must contain a party-culture keyword.
    if not (KEYWORD_PAT and KEYWORD_PAT.search(title)):
        if not is_niche(src):
            return None
    now = int(time.time())
    age = now - ts
    return {
        "title": strip_source(title),
        "link":  link or "#",
        "src":   src,
        "domain": domain or _guess_domain(src),
        "time":  time_label(age),
        "cat":   categorize(title),
        "hot":   age < BREAKING_HOURS * 3600,
        "ts":    ts,
        "tier":  source_tier(src),
        "n":     1,
    }

def filter_and_dedup(raw):
    """Filter, then collapse exact AND near-duplicate headlines.
    Near-dupes (Jaccard of significant words >= 0.55) are merged, keeping the
    higher-trust source. Each surviving story carries n = the number of DISTINCT
    sources that reported it (the 'most-reported' ranking signal)."""
    now = int(time.time())
    max_age = DAILY_HOURS * 3600
    raw.sort(key=lambda x: x[0], reverse=True)
    out, sigs, srcsets = [], [], []
    exact_idx = {}
    for tup in raw:
        ts, title, link, src = tup[0], tup[1], tup[2], tup[3]
        domain = tup[4] if len(tup) > 4 else ""
        if (now - ts) > max_age:
            continue
        it = build_item(ts, title, link, src, domain)
        if not it:
            continue
        srcid = (it.get("domain") or src or "").lower()
        h = hashlib.md5(_key(title).encode()).hexdigest()
        if h in exact_idx:
            j = exact_idx[h]
            if srcid:
                srcsets[j].add(srcid)
            out[j]["n"] = max(1, len(srcsets[j]))
            continue
        sg = _sigwords(title)
        dup = -1
        if sg:
            for i, prev in enumerate(sigs):
                if not prev:
                    continue
                inter = len(sg & prev)
                union = len(sg | prev)
                if union and (inter / union) >= 0.55:
                    dup = i
                    break
        if dup >= 0:
            if srcid:
                srcsets[dup].add(srcid)
            if it["tier"] < out[dup]["tier"]:
                it["n"] = max(1, len(srcsets[dup]))
                out[dup] = it
                sigs[dup] = sg
                exact_idx[h] = dup
            else:
                out[dup]["n"] = max(1, len(srcsets[dup]))
            continue
        exact_idx[h] = len(out)
        out.append(it)
        sigs.append(sg)
        srcsets.append(set([srcid]) if srcid else set())
        if len(out) >= MAX_ITEMS * 2:
            break
    out.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return out[:MAX_ITEMS]

# ──────────────── VEGAS EVENTS SCRAPER (No Cover Nightclubs) ────────────────
# Parses event URLs only (slugs carry artist+venue+date), so it survives any
# page-layout change. Writes events.json for the "On The Horizon" feed.
import calendar as _cal
_VG_MONTHS = {m.lower(): i for i, m in enumerate(_cal.month_name) if m}
_VG_WD = "monday tuesday wednesday thursday friday saturday sunday".split()
VG_VENUES = {
    "zouk-nightclub": ("Zouk", "club"), "xs-nightclub": ("XS", "club"),
    "omnia-nightclub": ("Omnia", "club"), "marquee-nightclub": ("Marquee", "club"),
    "tao-nightclub": ("Tao", "club"), "hakkasan-nightclub": ("Hakkasan", "club"),
    "liv-nightclub": ("LIV", "club"), "jewel-nightclub": ("Jewel", "club"),
    "ebc-at-night": ("EBC At Night", "club"), "ghostbar-nightclub": ("Ghostbar", "club"),
    "forty-deuce": ("Forty Deuce", "club"),
    "encore-beach-club": ("Encore Beach Club", "pool"), "marquee-dayclub": ("Marquee Dayclub", "pool"),
    "tao-beach": ("Tao Beach", "pool"), "tao-beach-dayclub": ("Tao Beach", "pool"),
    "liquid-pool": ("Liquid Pool", "pool"), "liquid": ("Liquid Pool", "pool"),
    "palm-tree-beach-club": ("Palm Tree Beach", "pool"), "liv-beach": ("LIV Beach", "pool"),
    "ayu-dayclub": ("AYU Dayclub", "pool"), "tailgate-beach-club": ("Tailgate Beach", "pool"),
    "stadium-swim": ("Stadium Swim", "pool"), "omnia-dayclub": ("Omnia Dayclub", "pool"),
}
_VG_SLUGS = sorted(VG_VENUES, key=len, reverse=True)
_VG_DATE_RE = re.compile(r"-(%s)-([a-z]+)-(\d{1,2})-(\d{4})(?:-\d+)?$" % "|".join(_VG_WD))
_VG_EVENT_RE = re.compile(r"https://nocovernightclubs\.com/events/[a-z0-9\-]+/?")
VG_CALENDARS = [
    "https://nocovernightclubs.com/zouk-nightclub-event-calendar/",
    "https://nocovernightclubs.com/xs-nightclub-event-calendar/",
    "https://nocovernightclubs.com/omnia-nightclub-las-vegas-event-calendar/",
    "https://nocovernightclubs.com/marquee-nightclub-las-vegas-event-calendar/",
    "https://nocovernightclubs.com/tao-nightclub-las-vegas-event-calendar/",
    "https://nocovernightclubs.com/hakkasan-nightclub-event-calendar/",
    "https://nocovernightclubs.com/liv-nightclub-event-calendar/",
    "https://nocovernightclubs.com/jewel-nightclub-event-calendar/",
    "https://nocovernightclubs.com/encore-beach-club-event-calendar/",
    "https://nocovernightclubs.com/marquee-dayclub-event-calendar/",
    "https://nocovernightclubs.com/tao-beach-event-calendar/",
    "https://nocovernightclubs.com/liquid-pool-event-calendar/",
    "https://nocovernightclubs.com/palm-tree-beach-club-event-calendar/",
    "https://nocovernightclubs.com/liv-beach-event-calendar/",
    "https://nocovernightclubs.com/ayu-dayclub-event-calendar/",
    "https://nocovernightclubs.com/tailgate-beach-club-event-calendar/",
]
def _vg_parse(url):
    slug = url.rstrip("/").split("/events/")[-1]
    m = _VG_DATE_RE.search(slug)
    if not m:
        return None
    _wd, mon, day, year = m.groups()
    if mon not in _VG_MONTHS:
        return None
    head = slug[:m.start()]
    vslug = None
    for vs in _VG_SLUGS:
        if head.endswith("-" + vs) or head == vs:
            vslug = vs
            break
    if not vslug:
        return None
    artist_slug = head[:-(len(vslug) + 1)] if head.endswith("-" + vslug) else ""
    if not artist_slug:
        return None
    artist = " ".join(w.capitalize() for w in artist_slug.split("-"))
    vname, vtype = VG_VENUES[vslug]
    ts = _cal.timegm((int(year), _VG_MONTHS[mon], int(day), 19, 0, 0, 0, 0, 0))
    return {"artist": artist, "venue": vname, "type": vtype, "city": "Las Vegas",
            "date": "%04d-%02d-%02d" % (int(year), _VG_MONTHS[mon], int(day)),
            "ts": ts, "url": url}

def scrape_vegas():
    found = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PartyPortalBot/2.3)"}
    for cal_url in VG_CALENDARS:
        try:
            req = urllib.request.Request(cal_url, headers=headers)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
                html = r.read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"  [VG WARN] {cal_url}: {e}")
            continue
        for m in _VG_EVENT_RE.finditer(html):
            ev = _vg_parse(m.group(0))
            if not ev:
                continue
            found[(ev["artist"], ev["venue"], ev["date"])] = ev
    cutoff = int(time.time()) - 36 * 3600
    return sorted([e for e in found.values() if e["ts"] >= cutoff], key=lambda x: x["ts"])[:120]


def load_prior():
    """Load the previous feed.json (if any) as raw tuples so yesterday's
    stories persist across runs — that's what fills the 'Earlier' column."""
    try:
        with open("feed.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for it in data.get("items", []):
            ts = int(it.get("ts") or 0)
            if not ts:
                continue
            out.append((ts, it.get("title", ""), it.get("link", "#"),
                        it.get("src", ""), it.get("domain", "")))
        return out
    except Exception:
        return []

# ─────────────────────────────── MAIN ──────────────────────────────
if __name__ == "__main__":
    print(f"[Party Portal Bot 2.0] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Keywords: {len(KEYWORDS)} | Sources: {len(CULTURE_SOURCES)}")
    print("  Fetching RSS…")
    raw = fetch_all()
    print(f"  Raw items (fresh): {len(raw)}")
    prior = load_prior()
    print(f"  Prior items (carried for 'Earlier'): {len(prior)}")
    raw = raw + prior
    items = filter_and_dedup(raw)
    multi = sum(1 for i in items if i.get("n", 1) >= 2)
    print(f"  After clean/filter/dedup: {len(items)} ({multi} multi-source)")
    if items:
        with open("feed.json", "w", encoding="utf-8") as f:
            json.dump({"updated": int(time.time()), "items": items}, f, ensure_ascii=False, indent=2)
        print(f"[OK] feed.json written — {len(items)} real items")
    else:
        print("[WARN] No real items passed the filters — feed.json left unchanged (no synthetic data).")
    # ── Vegas events (No Cover Nightclubs) ──
    try:
        print("  Scraping Vegas club & dayclub calendars…")
        vg = scrape_vegas()
        if len(vg) >= 8:
            with open("events.json", "w", encoding="utf-8") as f:
                json.dump({"updated": int(time.time()), "events": vg}, f, ensure_ascii=False, indent=2)
            print(f"[OK] events.json written — {len(vg)} Vegas events")
        else:
            print(f"[VG] only {len(vg)} events parsed — keeping existing events.json (no overwrite)")
    except Exception as e:
        print(f"[VG ERROR] {e} — events.json left unchanged")
    print("[Done]")
