#!/usr/bin/env python3
"""
PARTY PORTAL — Content Bot
Based on NUZU culture bot architecture.
Fetches party/festival/nightlife culture news from Google News RSS,
filters by party-culture keywords, deduplicates, and injects into index.html.

Run: python bot.py
GitHub Actions trigger: daily at 6 AM UTC
"""

import os, re, json, time, hashlib, html as htmllib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET
import urllib.request, urllib.error

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
MAX_ITEMS       = 40      # max culture items to display
BREAKING_HOURS  = 48      # items < 48h old are "breaking"
DAILY_HOURS     = 96      # items < 96h old are "latest"
FETCH_TIMEOUT   = 12      # seconds per RSS request
MAX_WORKERS     = 12      # concurrent RSS fetches
MIN_TITLE_LEN   = 30
MAX_TITLE_LEN   = 280
INDEX_PATH      = 'index.html'
INJECT_MARKER   = '<!-- PP_CULTURE_INJECT -->'

# ─────────────────────────────────────────────────────────────
#  PARTY CULTURE KEYWORDS
#  (NUZU culture base + extensive party/festival additions)
# ─────────────────────────────────────────────────────────────
RAW_KEYWORDS = [
    # ── Core party/festival ──────────────────────────────────
    "edm festival","electronic music festival","music festival 2026",
    "electric daisy carnival","edc las vegas","edc 2026",
    "coachella","coachella 2026","coachella festival",
    "coachella lineup","coachella headliner",
    "ultra music festival","ultra miami","ultra 2026",
    "tomorrowland","tomorrowland 2026","tomorrowland belgium",
    "tomorrowland winter","tomorrowland brazil",
    "glastonbury","glastonbury 2026","glastonbury festival",
    "lollapalooza","lollapalooza 2026","lollapalooza chicago",
    "bonnaroo","bonnaroo 2026",
    "burning man","burning man 2026","black rock city",
    "creamfields","creamfields 2026",
    "lost lands festival","awakenings festival",
    "lucidity festival","day trip festival",
    "ibiza festival","ibiza club season","ibiza 2026",
    "ushuaia ibiza","dc10 ibiza","fabric london",
    "festival lineup","festival headliner","festival announcement",
    "festival tickets","festival season 2026",
    "music festival news","festival news 2026",
    # ── Electronic music ─────────────────────────────────────
    "edm news","dance music news","electronic music news",
    "dj set","live dj","dj residency","dj tour 2026",
    "techno festival","house music festival","trance festival",
    "dubstep festival","bass music","bass festival",
    "rave","rave culture","underground rave",
    "beatport chart","resident advisor","mixmag festival",
    "dj mag","dancing astronaut","edm.com",
    "hardstyle festival","drum and bass festival",
    "electronic dance music","progressive house",
    "festival dj","festival stage","mainstage",
    # ── Nightlife/venues ─────────────────────────────────────
    "nightlife","nightclub news","club night","club culture",
    "vegas nightclub","las vegas entertainment","vegas strip party",
    "las vegas shows","las vegas nightlife 2026",
    "bourbon street","new orleans nightlife","mardi gras",
    "mardi gras 2026","new orleans party",
    "key west bar","key west nightlife","duval street",
    "ibiza nightclub","ibiza party","ibiza season",
    "miami nightlife","miami beach party","miami art basel",
    "new york nightlife","nyc club","manhattan nightlife",
    "berlin techno","berlin club","berlin nightlife",
    "amsterdam nightlife","amsterdam club",
    "london nightlife","london club scene",
    "club opening","bar scene","nightclub review",
    # ── Specific venues/events ───────────────────────────────
    "bellagio fountain","las vegas sphere","sphere las vegas",
    "times square new year","times square celebration",
    "hogs breath key west","sloppy joe's key west",
    # ── Culture (NUZU base, party-adjacent) ──────────────────
    "celebrity news","hollywood news","pop culture news",
    "viral moment","trending topic","internet culture",
    "festival fashion 2026","coachella fashion","rave outfit",
    "festival outfit","festival style","festival looks",
    "glastonbury fashion","burning man costumes",
    "billboard","rolling stone music","pitchfork music",
    "nme music","stereogum","consequence of sound",
    "concert tour 2026","touring artist 2026",
    "music tour announcement","tour dates 2026",
    "grammy awards music","grammy 2026",
    "sxsw 2026","south by southwest music",
    "bonnaroo festival","outside lands festival",
    "governor's ball festival","firefly music festival",
    "splendour in the grass","reading festival",
    "download festival","bestival","worthy farm",
    # ── Artist/performer ─────────────────────────────────────
    "pretty lights live","astrix live","classmatic",
    "tiesto","martin garrix","david guetta","calvin harris",
    "deadmau5","skrillex","diplo","marshmello",
    "afrojack","armin van buuren","above beyond",
    "eric prydz","bicep live","four tet live",
    "jamie jones","charlotte de witte","adam beyer",
    "richie hawtin","nina kraviz","peggy gou",
    "amelie lens","helena hauff","paul kalkbrenner",
    # ── Broad culture (inherited from NUZU) ──────────────────
    "entertainment news","film industry news","box office updates",
    "movie premieres","celebrity interviews","streaming services",
    "netflix celebrity","hbo celebrity","award show",
    "met gala","red carpet fashion","vogue covers",
    "fashion trends","street style","beauty trends",
    "influencer fashion","tiktok influencers","content creators",
    "viral entertainment","trending celebrity","social media",
    "world cup culture","host city celebration","fan zone 2026",
    "art basel miami 2026","frieze art fair","venice biennale",
    "summer concerts 2026","outdoor concert","amphitheater show",
    "pop star tour","rock concert 2026","hip hop show",
    "rap concert","festival rap","hip hop festival",
    "taylor swift","beyonce concert","rihanna tour",
    "dua lipa concert","the weeknd tour","drake concert",
    "bad bunny tour","j balvin concert","reggaeton festival",
]

KEYWORDS = set(kw.lower() for kw in RAW_KEYWORDS)

def make_pattern(kw_set):
    escaped = [re.escape(k) for k in sorted(kw_set, key=len, reverse=True)]
    return re.compile(r'\b(?:' + '|'.join(escaped) + r')\b', re.IGNORECASE) if escaped else None

KEYWORD_PAT = make_pattern(KEYWORDS)

# strict blocklist — keep feed party-positive
BLOCKLIST = {
    "war","bombing","missile","attack","massacre","genocide","terrorist",
    "shooting","murder","crime","arrest","lawsuit","controversy",
    "scandal","abuse","harassment","assault","conviction","prison",
    "inflation","recession","stock market","fed rate","federal reserve",
    "immigration","border","deportation","politics","election",
    "republican","democrat","congress","senate","white house",
    "foreign policy","nato","ukraine","iran","israel","palestine",
}
BLOCK_PAT = make_pattern(BLOCKLIST)

# ─────────────────────────────────────────────────────────────
#  RSS SOURCES — party/festival/nightlife culture focused
# ─────────────────────────────────────────────────────────────
CULTURE_SOURCES = [
    # Party / Festival direct
    ("Party Festival",      "https://news.google.com/rss/search?q=music+festival+2026+OR+festival+lineup+OR+EDM+festival+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("EDC Las Vegas",       "https://news.google.com/rss/search?q=electric+daisy+carnival+OR+EDC+Las+Vegas+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Coachella News",      "https://news.google.com/rss/search?q=coachella+festival+lineup+OR+coachella+2026+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Tomorrowland",        "https://news.google.com/rss/search?q=tomorrowland+festival+OR+tomorrowland+2026+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Ultra Music Fest",    "https://news.google.com/rss/search?q=ultra+music+festival+OR+ultra+miami+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Glastonbury",         "https://news.google.com/rss/search?q=glastonbury+festival+2026+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Burning Man",         "https://news.google.com/rss/search?q=burning+man+2026+OR+burning+man+festival+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("EDM News",            "https://news.google.com/rss/search?q=edm+news+OR+dance+music+news+OR+electronic+music+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("DJ News",             "https://news.google.com/rss/search?q=dj+residency+OR+dj+tour+OR+dj+set+announcement+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Nightlife",           "https://news.google.com/rss/search?q=nightlife+guide+OR+nightclub+OR+club+night+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Ibiza",               "https://news.google.com/rss/search?q=ibiza+club+OR+ibiza+season+OR+ushuaia+ibiza+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Vegas Party",         "https://news.google.com/rss/search?q=las+vegas+nightlife+OR+vegas+nightclub+OR+las+vegas+entertainment+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("New Orleans",         "https://news.google.com/rss/search?q=bourbon+street+OR+new+orleans+nightlife+OR+mardi+gras+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Miami Nightlife",     "https://news.google.com/rss/search?q=miami+nightlife+OR+miami+beach+party+OR+miami+art+basel+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Lollapalooza",        "https://news.google.com/rss/search?q=lollapalooza+2026+OR+lollapalooza+lineup+when:3d&hl=en-US&gl=US&ceid=US:en"),
    ("Rave Culture",        "https://news.google.com/rss/search?q=rave+culture+OR+underground+rave+OR+techno+festival+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Festival Fashion",    "https://news.google.com/rss/search?q=coachella+fashion+OR+festival+outfit+OR+rave+outfit+when:2d&hl=en-US&gl=US&ceid=US:en"),
    # Broad culture (from NUZU, party-adjacent)
    ("Billboard",           "https://news.google.com/rss/search?q=billboard+music+news+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Rolling Stone",       "https://news.google.com/rss/search?q=rolling+stone+music+celebrity+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Pitchfork",           "https://news.google.com/rss/search?q=pitchfork+music+news+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("NME",                 "https://news.google.com/rss/search?q=nme+music+celebrity+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Variety Music",       "https://news.google.com/rss/search?q=variety+music+concert+tour+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Mixmag",              "https://news.google.com/rss/search?q=mixmag+electronic+music+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("DJ Mag",              "https://news.google.com/rss/search?q=dj+magazine+electronic+music+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Resident Advisor",    "https://news.google.com/rss/search?q=resident+advisor+electronic+music+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Concert Tour",        "https://news.google.com/rss/search?q=concert+tour+2026+OR+tour+dates+announcement+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("SXSW",                "https://news.google.com/rss/search?q=sxsw+2026+OR+south+by+southwest+music+when:3d&hl=en-US&gl=US&ceid=US:en"),
    ("Broad Culture",       "https://news.google.com/rss/search?q=celebrity+news+OR+hollywood+OR+pop+culture+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Entertainment",       "https://news.google.com/rss/search?q=entertainment+news+celebrity+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Outdoor Events",      "https://news.google.com/rss/search?q=outdoor+concert+2026+OR+amphitheater+show+OR+summer+concert+when:2d&hl=en-US&gl=US&ceid=US:en"),
]

# ─────────────────────────────────────────────────────────────
#  RSS FETCH + PARSE
# ─────────────────────────────────────────────────────────────
def _fetch_rss(name, url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; PartyPortalBot/1.0)',
        'Accept': 'application/rss+xml, application/xml, text/xml',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []
        for item in root.iter('item'):
            title_el = item.find('title')
            link_el  = item.find('link')
            pub_el   = item.find('pubDate')
            src_el   = item.find('{https://news.google.com/rss}source') or item.find('source')
            if title_el is None or not title_el.text:
                continue
            title = htmllib.unescape(title_el.text.strip())
            link  = (link_el.text or '').strip() if link_el is not None else ''
            src   = src_el.text.strip() if src_el is not None and src_el.text else name
            # parse pub date
            ts = 0
            if pub_el is not None and pub_el.text:
                for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT',
                            '%a, %d %b %Y %H:%M:%S +0000'):
                    try:
                        dt = datetime.strptime(pub_el.text.strip(), fmt)
                        ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt.tzinfo is None else int(dt.timestamp())
                        break
                    except ValueError:
                        pass
            if not ts:
                ts = int(time.time()) - 3600
            items.append((ts, title, link, src))
        return items
    except Exception as e:
        print(f'  [WARN] {name}: {e}')
        return []

def fetch_all():
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_rss, n, u): n for n, u in CULTURE_SOURCES}
        for f in as_completed(futures):
            results.extend(f.result())
    return results

# ─────────────────────────────────────────────────────────────
#  FILTER + DEDUPLICATE
# ─────────────────────────────────────────────────────────────
def _title_key(title):
    """Normalize title for dedup."""
    t = re.sub(r'\s*[-–|:]\s*\w[\w\s]+$', '', title)  # strip "- Source Name"
    t = re.sub(r'[^a-z0-9 ]', '', t.lower())
    return ' '.join(t.split()[:12])

def _item_hash(title):
    return hashlib.md5(_title_key(title).encode()).hexdigest()

def filter_and_dedup(raw_items):
    now = int(time.time())
    max_age = DAILY_HOURS * 3600
    seen_hashes = set()
    results = []
    raw_items.sort(key=lambda x: x[0], reverse=True)  # newest first

    for ts, title, link, src in raw_items:
        # age filter
        if (now - ts) > max_age:
            continue
        # length filter
        if len(title) < MIN_TITLE_LEN or len(title) > MAX_TITLE_LEN:
            continue
        # blocklist
        if BLOCK_PAT and BLOCK_PAT.search(title):
            continue
        # keyword match
        if KEYWORD_PAT and not KEYWORD_PAT.search(title):
            # still accept if from a highly relevant source
            relevant_sources = {'billboard','rolling stone','pitchfork','nme','mixmag','dj mag',
                                 'resident advisor','edm.com','dancing astronaut','festicket'}
            if src.lower() not in relevant_sources:
                continue
        # dedup
        h = _item_hash(title)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        # classify
        hot = (now - ts) < BREAKING_HOURS * 3600
        age_sec = now - ts
        if age_sec < 3600:
            time_label = f'{max(1, age_sec // 60)} min ago'
        elif age_sec < 86400:
            time_label = f'{age_sec // 3600} hr ago'
        elif age_sec < 172800:
            time_label = '1 day ago'
        else:
            time_label = f'{age_sec // 86400} days ago'

        # category tag
        t_lower = title.lower()
        if any(w in t_lower for w in ['festival','lineup','headliner','coachella','edc','tomorrowland','ultra','glastonbury','lollapalooza','burning man','creamfields','lost lands','awakenings']):
            cat = 'Festival'
        elif any(w in t_lower for w in ['nightclub','club night','nightlife','rave','ibiza','vegas club']):
            cat = 'Nightlife'
        elif any(w in t_lower for w in ['dj','edm','electronic music','techno','house music','dance music']):
            cat = 'EDM'
        elif any(w in t_lower for w in ['concert','tour','live show','ticket','venue']):
            cat = 'Concert'
        elif any(w in t_lower for w in ['fashion','outfit','style','looks','trend']):
            cat = 'Fashion'
        else:
            cat = 'Culture'

        results.append({
            'title': title,
            'link':  link,
            'src':   src,
            'time':  time_label,
            'cat':   cat,
            'hot':   hot,
            'ts':    ts,
        })

        if len(results) >= MAX_ITEMS * 2:
            break

    return results[:MAX_ITEMS]

# ─────────────────────────────────────────────────────────────
#  INJECT INTO index.html
# ─────────────────────────────────────────────────────────────
def inject_into_html(items):
    if not os.path.exists(INDEX_PATH):
        print(f'[ERROR] {INDEX_PATH} not found')
        return False

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # Remove any previous injection
    html = re.sub(r'<!-- PP_CULTURE_INJECT -->\s*<script>.*?</script>', INJECT_MARKER, html, flags=re.DOTALL)

    now_ts = int(time.time())
    items_json = json.dumps(items, ensure_ascii=False)
    inject = (
        INJECT_MARKER + '\n'
        f'<script>window._ppCultureItems={items_json};window._ppUpdatedTs={now_ts};</script>'
    )
    if INJECT_MARKER in html:
        html = html.replace(INJECT_MARKER, inject, 1)
        with open(INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'[OK] Injected {len(items)} culture items into {INDEX_PATH}')
        return True
    else:
        print(f'[WARN] Inject marker not found in {INDEX_PATH}')
        return False

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'[Party Portal Bot] Starting at {datetime.now(timezone.utc).isoformat()}')
    print(f'  Keywords: {len(KEYWORDS)} | Sources: {len(CULTURE_SOURCES)}')

    print('  Fetching RSS...')
    raw = fetch_all()
    print(f'  Raw items fetched: {len(raw)}')

    items = filter_and_dedup(raw)
    print(f'  After filter/dedup: {len(items)} items')

    if items:
        inject_into_html(items)
        # also write a feed.json for external consumption
        with open('feed.json', 'w', encoding='utf-8') as f:
            json.dump({'updated': int(time.time()), 'items': items}, f, ensure_ascii=False, indent=2)
        print('[OK] feed.json written')
    else:
        print('[WARN] No items after filtering — index.html not modified')

    print('[Done]')
