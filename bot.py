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
import urllib.request, urllib.parse, urllib.error

# ───────────────────────────── CONFIG ─────────────────────────────
MAX_ITEMS      = 60
PER_SOURCE_MAX = 4      # max stories per outlet PER DAY (diversity, both days)
PER_DAY_MAX    = 30     # max stories kept per calendar day
BREAKING_HOURS = 36     # < 36h old  → "hot"
DAILY_HOURS    = 50     # < 50h old  → kept (today + yesterday, with margin)
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
    # rock 'n' roll / live bands
    "rock concert","rock festival","rock tour","reunion tour","stadium tour","world tour",
    "headlining tour","arena tour","farewell tour","greatest hits tour","anniversary tour",
    "foo fighters","metallica","red hot chili peppers","green day","guns n roses","pearl jam",
    "the rolling stones","ac/dc","muse","arctic monkeys","blink-182","paramore","kings of leon",
    "punk","alt rock","classic rock","rock band","headline glastonbury","download festival",
    # hip-hop / rap live
    "hip hop festival","rap concert","hip hop concert","rolling loud","rap residency",
    "drake","travis scott","kendrick lamar","tyler the creator","don toliver","meek mill",
    # nightlife venues / vegas / ibiza
    "sphere residency","drai's","hakkasan","omnia","xs nightclub","encore beach club","wet republic",
    "marquee nightclub","liv nightclub","zouk nightclub","tao nightclub","day club","beach club",
    "superstar dj","headline set","sunset set","closing set","opening party","season opening",
    "afterparty","warehouse rave","techno rave","trance family","psytrance","ozora","boom festival",
    "defected","glitterbox","anjunabeats","anjunadeep","cercle","afterlife","drumcode","elrow",
]

# ── Party Portal 2.0 keyword expansion — deeper party-culture coverage ──
RAW_KEYWORDS += [
    # global nightlife capitals & districts
    "berghain","tresor","fabric london","printworks","ministry of sound","razzmatazz",
    "hi ibiza","ushuaia ibiza","amnesia","privilege ibiza","eden ibiza","o beach",
    "space miami","club space","e11even","liv miami","story miami","exchange la",
    "academy la","sound nightclub","output brooklyn","brooklyn mirage","avant gardner",
    "webster hall","house of yes","elsewhere brooklyn","smartbar chicago","radius chicago",
    "concord music hall","stereo montreal","womb tokyo","zouk singapore","green valley brazil",
    "shibuya nightlife","roppongi","seoul nightlife","bangkok nightlife","tulum party",
    "papaya playa","zamna tulum","art with me","day zero tulum",
    # counterculture / scene
    "underground rave","free party","warehouse rave","illegal rave","squat party",
    "sound system","dub sound system","block party","street party","carnival",
    "notting hill carnival","mardi gras","spring break","full moon party","boat party",
    "silent disco","afterhours","after party","dayclub","day club","pool club",
    "burner","playa","default world","theme camp","art car","regional burn",
    # music scenes / genres
    "hardstyle","hardcore techno","gabber","jungle","breakbeat","uk garage","speed garage",
    "amapiano","afro house","afrobeats","baile funk","reggaeton","dembow","cumbia",
    "hyperpop","jersey club","footwork","ghettotech","minimal techno","acid techno",
    "progressive house","deep house","tech house","organic house","downtempo","psybient",
    "goa trance","full on psytrance","dark psytrance","forest psy","hi tech psy",
    # industry / events
    "residency announcement","tour announcement","lineup announced","phase one lineup",
    "set times","festival map","ticket presale","general admission","vip table",
    "bottle service","guest list","promoter","talent buyer","booking agent",
    "amf","amsterdam dance event","ade","miami music week","winter music conference",
    "sonar barcelona","time warp","awakenings festival","dekmantel","dour festival",
    "exit festival","sziget","primavera sound","fuji rock","rock in rio","tomorrowland brasil",
    "electric zoo","edc mexico","edc japan","beyond wonderland","nocturnal wonderland",
    "escape halloween","countdown nye","hard summer","framework la","insomniac",
    "brownies and lemonade","secret project","portola","north coast","imagine festival",
    # fashion / culture crossovers
    "festival fashion","rave fashion","runway show","swim week","resort collection",
    "fashion week","street style","y2k fashion","rave wear","club kid",
    # retro / MTV lineage
    "mtv","vh1","music video","music television","trl","yo mtv raps","headbangers ball",
    "120 minutes","unplugged","soul train","top of the pops","muchmusic","spring break mtv",
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
    "verdict","trial","testimony","deposition","settlement","restraining order","subpoena",
    "hospitalized","health scare","cancer","rehab","custody","alimony","divorce","tax evasion",
    "fraud","scam","backlash","slams","slammed","feud","diss track","clap back","apologizes",
    "misconduct","accuser","accused of","allegations","sexual misconduct","stabbed","gunman",
    "dies aged","dies at","died at","dies in","died in","found dead","shot dead","has died",
    "passed away","helicopter crash","plane crash","fatal","shots rang","shots fired","person shot",
    "people shot","mass shooting","killed in","death of","stabbing","wounded","critical condition",
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
    "edm sauce","data transmission","decoded magazine","when we dip","mixmag asia","dj times",
    "the nocturnal times","ravejungle","run the trap","loudwire","ultimate classic rock",
    "kerrang","revolver","metal injection","hotnewhiphop","xxl","hiphopdx","rap-up",
    "edm maniac","music festival wizard","ibiza spotlight","electronic vegas","rave jungle",
}
NICHE_SOURCES = {  # accepted on-topic even without a generic keyword hit
    "mixmag","dj mag","djmag","resident advisor","edm.com","dancing astronaut","edmtunes",
    "your edm","we rave you","6am","magnetic magazine","magnetic mag","electronic groove",
    "edm identity","attack magazine","ra","edm sauce","data transmission","decoded magazine",
    "when we dip","mixmag asia","dj times","the nocturnal times","ravejungle","run the trap",
    "edm maniac","ibiza spotlight","electronic vegas",
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
    ("Rolling Stone",     g("site:rollingstone.com+festival+OR+electronic+OR+dj+OR+tour+when:2d")),
    ("Pitchfork",         g("site:pitchfork.com+festival+OR+electronic+when:3d")),
    ("NME",               g("site:nme.com+festival+OR+dance+OR+tour+when:3d")),
    ("DJ Tours",          g("dj+residency+OR+dj+tour+2026+OR+b2b+set+when:2d")),
    ("Festival Fashion",  g("coachella+fashion+OR+festival+outfit+OR+rave+outfit+when:3d")),
    # more EDM / dance specialists
    ("EDM Identity",      g("site:edmidentity.com+when:4d")),
    ("EDM Sauce",         g("site:edmsauce.com+when:4d")),
    ("Data Transmission", g("site:datatransmission.co+when:5d")),
    ("Decoded Magazine",  g("site:decodedmagazine.com+when:5d")),
    ("When We Dip",       g("site:whenwedip.com+when:5d")),
    # ── Party Portal 2.0 source expansion ──
    ("Mixmag Asia",       g("site:mixmag.asia+when:4d")),
    ("DJ Mag North Am",   g("site:djmag.com+north+america+OR+festival+when:3d")),
    ("Ibiza Spotlight",   g("site:ibiza-spotlight.com+when:4d")),
    ("Beatportal",        g("site:beatportal.com+when:4d")),
    ("Attack Magazine",   g("site:attackmagazine.com+when:5d")),
    ("XLR8R",             g("site:xlr8r.com+when:5d")),
    ("Rave Jungle",       g("site:ravejungle.com+when:4d")),
    ("EDM Maniac",        g("site:edmmaniac.com+when:4d")),
    ("Festival Wizard",   g("site:musicfestivalwizard.com+when:4d")),
    ("Time Out Nightlife",g("site:timeout.com+nightlife+OR+club+OR+bar+when:3d")),
    ("Berlin Techno",     g("berghain+OR+tresor+OR+berlin+techno+when:4d")),
    ("London Clubbing",   g("fabric+london+OR+printworks+OR+london+nightlife+when:3d")),
    ("Amsterdam / ADE",   g("amsterdam+dance+event+OR+ADE+2026+OR+awakenings+when:4d")),
    ("Tulum / Mexico",    g("tulum+party+OR+zamna+OR+day+zero+tulum+when:4d")),
    ("Brazil / LatAm",    g("rock+in+rio+OR+tomorrowland+brasil+OR+baile+funk+when:4d")),
    ("Asia Nightlife",    g("tokyo+nightlife+OR+seoul+club+OR+zouk+singapore+when:4d")),
    ("Australia Scene",   g("sydney+nightlife+OR+melbourne+club+OR+australia+festival+when:4d")),
    ("Amapiano / Afro",   g("amapiano+OR+afro+house+OR+afrobeats+party+when:3d")),
    ("Psytrance Scene",   g("psytrance+festival+OR+ozora+OR+boom+festival+when:4d")),
    ("Hardstyle",         g("hardstyle+OR+defqon+OR+qlimax+OR+hardcore+techno+when:4d")),
    ("Drum & Bass",       g("drum+and+bass+OR+jungle+OR+liquid+dnb+when:3d")),
    ("Insomniac Events",  g("insomniac+events+OR+beyond+wonderland+OR+escape+halloween+when:4d")),
    ("Fashion / Runway",  g("swim+week+OR+resort+collection+OR+runway+show+when:3d")),
    ("Retro MTV",         g("mtv+throwback+OR+music+video+anniversary+OR+90s+nostalgia+when:4d")),
    ("Counterculture",    g("underground+rave+OR+free+party+OR+sound+system+culture+when:4d")),
    ("New Orleans Scene", g("frenchmen+street+OR+new+orleans+jazz+OR+mardi+gras+when:4d")),
    ("Austin / Texas",    g("austin+music+OR+sxsw+OR+texas+festival+when:4d")),
    ("Denver / Red Rocks",g("red+rocks+OR+denver+nightlife+OR+colorado+festival+when:4d")),
    ("LA Nightlife",      g("los+angeles+nightlife+OR+hollywood+club+OR+la+warehouse+when:3d")),
    ("NYC Nightlife",     g("brooklyn+mirage+OR+nyc+nightlife+OR+house+of+yes+when:3d")),
    ("Mixmag Asia",       g("site:mixmag.asia+when:5d")),
    ("Attack Magazine",   g("site:attackmagazine.com+when:5d")),
    ("Ibiza Spotlight",   g("site:ibiza-spotlight.com+when:4d")),
    ("EDM Maniac",        g("site:edmmaniac.com+when:4d")),
    # rock 'n' roll / live bands (keyword-filtered to stay party/live-focused)
    ("Loudwire",          g("site:loudwire.com+tour+OR+festival+OR+reunion+OR+concert+when:3d")),
    ("Ultimate Classic Rock", g("site:ultimateclassicrock.com+tour+OR+festival+OR+residency+when:4d")),
    ("Brooklyn Vegan",    g("site:brooklynvegan.com+festival+OR+tour+OR+lineup+when:3d")),
    ("Consequence",       g("site:consequence.net+festival+OR+tour+OR+lineup+OR+rave+when:2d")),
    ("Rock Tours",        g("rock+band+tour+2026+OR+stadium+tour+OR+reunion+tour+OR+world+tour+when:2d")),
    # hip-hop / rap live (Vegas books a lot of rap headliners)
    ("HipHopDX",          g("site:hiphopdx.com+festival+OR+tour+OR+concert+OR+vegas+when:3d")),
    ("Rolling Loud / Rap Live", g("rolling+loud+OR+rap+concert+OR+hip+hop+festival+OR+rap+residency+when:3d")),
    # festivals + nightlife extras
    ("Music Festival Wizard", g("site:musicfestivalwizard.com+when:3d")),
    ("Las Vegas Nightlife", g("las+vegas+pool+party+OR+vegas+dayclub+OR+vegas+dj+residency+when:3d")),
    ("Time Out Clubs",    g("site:timeout.com+nightlife+OR+club+OR+dj+OR+party+when:3d")),
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
                            "creamfields","lost lands","awakenings","iii points","outside lands",
                            "rolling loud","download festival","ozora","boom festival"]):
        return "Festival"
    if any(w in t for w in ["sphere","las vegas","vegas","encore beach","wet republic","hakkasan",
                            "omnia","xs nightclub","drai","marquee","zouk","liv nightclub","tao "]):
        return "Vegas"
    if any(w in t for w in ["rock","punk","metal","foo fighters","metallica","pearl jam","green day",
                            "guns n roses","rolling stones","ac/dc","muse","arctic monkeys","blink-182",
                            "paramore","kings of leon","band reunites","reunion tour"]):
        return "Rock"
    if any(w in t for w in ["hip hop","hip-hop","rap ","rapper","drake","travis scott","kendrick",
                            "tyler the creator","don toliver","meek mill","2 chainz","nelly"]):
        return "Hip-Hop"
    if any(w in t for w in ["nightclub","club night","nightlife","rave","ibiza","warehouse",
                            "after hours","bourbon street","mardi gras","pool party","day club",
                            "beach club","afterparty"]):
        return "Nightlife"
    if any(w in t for w in ["dj","edm","electronic","techno","house music","dance music","trance",
                            "boiler room","dubstep","hardstyle","drum and bass","psytrance","b2b"]):
        return "EDM"
    if any(w in t for w in ["fashion","outfit","style","runway","looks","swimsuit","bikini"]):
        return "Fashion"
    if any(w in t for w in ["concert","tour","live show","residency","ticket","amphitheater","arena"]):
        return "Concert"
    # ── Party Portal 2.0: finer-grained tags ──
    if any(w in t for w in ["techno","warehouse","berghain","tresor","fabric","boiler room",
                            "underground","acid","industrial techno","hard techno"]):
        return "Techno"
    if any(w in t for w in ["psytrance","psy-trance","goa","ozora","boom festival","psybient",
                            "forest psy","full on"]):
        return "Psytrance"
    if any(w in t for w in ["ibiza","amnesia","ushuaia","pacha","dc10","hi ibiza","balearic",
                            "o beach","privilege"]):
        return "Ibiza"
    if any(w in t for w in ["tulum","zamna","day zero","art with me","papaya playa",
                            "burning man","playa","regional burn","theme camp"]):
        return "Desert"
    if any(w in t for w in ["amapiano","afro house","afrobeats","baile funk","reggaeton",
                            "cumbia","dembow","global"]):
        return "Global"
    if any(w in t for w in ["mtv","vh1","music video","trl","retro","throwback","90s","80s",
                            "y2k","soul train","top of the pops","muchmusic"]):
        return "Retro"
    if any(w in t for w in ["pool party","dayclub","day club","beach club","spring break",
                            "boat party","full moon party","yacht"]):
        return "Pool"
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
    "decoded magazine": "decodedmagazine.com", "when we dip": "whenwedip.com",
    "mixmag asia": "mixmag.asia", "attack magazine": "attackmagazine.com",
    "ibiza spotlight": "ibiza-spotlight.com", "edm maniac": "edmmaniac.com",
    "ultimate classic rock": "ultimateclassicrock.com", "brooklyn vegan": "brooklynvegan.com",
    "hiphopdx": "hiphopdx.com", "music festival wizard": "musicfestivalwizard.com",
    "time out": "timeout.com", "revolver": "revolvermag.com", "metal injection": "metalinjection.net",
    "xxl": "xxlmag.com", "rap-up": "rap-up.com", "edm identity": "edmidentity.com",
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

def _base_domain(d):
    """Collapse regional subdomains (fr.ra.co, de.ra.co → ra.co) so one outlet
    can't dodge the per-source cap via country editions."""
    if not d or "." not in d:
        return d
    return ".".join(d.split(".")[-2:])

def _day_key(ts):
    """Pacific-time calendar day (UTC-7), matching the site's local-day news
    columns, so 'today' and 'yesterday' line up between bot and page."""
    return time.strftime("%Y-%m-%d", time.gmtime(int(ts) - 7 * 3600))

def filter_and_dedup(raw):
    """Filter, then collapse exact AND near-duplicate headlines.
    Near-dupes (Jaccard of significant words >= 0.55) are merged, keeping the
    higher-trust source. Each surviving story carries n = the number of DISTINCT
    sources that reported it (the 'most-reported' ranking signal). A per-source
    cap keeps any single outlet from flooding the feed (and starving older days)."""
    now = int(time.time())
    max_age = DAILY_HOURS * 3600
    raw.sort(key=lambda x: x[0], reverse=True)
    out, sigs, srcsets = [], [], []
    exact_idx = {}
    src_count = {}
    for tup in raw:
        ts, title, link, src = tup[0], tup[1], tup[2], tup[3]
        domain = tup[4] if len(tup) > 4 else ""
        if (now - ts) > max_age:
            continue
        it = build_item(ts, title, link, src, domain)
        if not it:
            continue
        srcid = _base_domain((it.get("domain") or src or "").lower())
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
        # per-source-per-DAY cap: each outlet may contribute to BOTH days,
        # so yesterday's stories are never starved out by today's flood.
        ck = (srcid, _day_key(ts))
        if src_count.get(ck, 0) >= PER_SOURCE_MAX:
            continue
        src_count[ck] = src_count.get(ck, 0) + 1
        exact_idx[h] = len(out)
        out.append(it)
        sigs.append(sg)
        srcsets.append(set([srcid]) if srcid else set())
        if len(out) >= MAX_ITEMS * 3:
            break
    # Keep the two most-recent days, each ranked by # sources then recency and
    # capped — guarantees TODAY *and* EARLIER both populate (NUZU-style).
    byday = {}
    for it in out:
        byday.setdefault(_day_key(it.get("ts", 0)), []).append(it)
    final = []
    for d in sorted(byday.keys(), reverse=True)[:2]:
        day_items = sorted(byday[d], key=lambda x: (x.get("n", 1), x.get("ts", 0)), reverse=True)
        final.extend(day_items[:PER_DAY_MAX])
    final.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return final[:MAX_ITEMS]

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
# ══════════════ GLOBAL EVENT HARVESTER (Party Portal 2.0) ══════════════
# The horizon calendar used to be ~100% Las Vegas. This widens it to the rest of
# the Southwest, Los Angeles, the whole US and the world, using the Ticketmaster
# Discovery API (free tier). It is OPTIONAL and FAIL-SAFE, exactly like
# curate.py's YouTube key: with no TICKETMASTER_API_KEY set it returns [] and the
# Vegas scraper's results are used unchanged. Set the GitHub secret to switch on.
#
# Add or remove cities in TM_MARKETS below — that is the only dial you need.
TM_KEY = os.environ.get("TICKETMASTER_API_KEY", "").strip()
TM_API = "https://app.ticketmaster.com/discovery/v2/events.json"
TM_PER_MARKET = 12          # events pulled per city per run
TM_DAYS_AHEAD  = 45         # how far forward to look

# (label, city, countryCode, our event "type")
TM_MARKETS = [
    # ── Southwest / desert circuit ──
    ("Las Vegas",     "Las Vegas",     "US", "club"),
    ("Phoenix",       "Phoenix",       "US", "club"),
    ("Scottsdale",    "Scottsdale",    "US", "club"),
    ("Tucson",        "Tucson",        "US", "concert"),
    ("Albuquerque",   "Albuquerque",   "US", "concert"),
    ("Salt Lake City","Salt Lake City","US", "concert"),
    # ── California ──
    ("Los Angeles",   "Los Angeles",   "US", "club"),
    ("Hollywood",     "Hollywood",     "US", "club"),
    ("San Diego",     "San Diego",     "US", "club"),
    ("San Francisco", "San Francisco", "US", "concert"),
    ("Palm Springs",  "Palm Springs",  "US", "pool"),
    # ── rest of the US ──
    ("Miami",         "Miami",         "US", "club"),
    ("New York",      "New York",      "US", "club"),
    ("Chicago",       "Chicago",       "US", "concert"),
    ("Austin",        "Austin",        "US", "concert"),
    ("New Orleans",   "New Orleans",   "US", "club"),
    ("Denver",        "Denver",        "US", "concert"),
    ("Atlanta",       "Atlanta",       "US", "club"),
    ("Nashville",     "Nashville",     "US", "concert"),
    ("Seattle",       "Seattle",       "US", "concert"),
    ("Detroit",       "Detroit",       "US", "concert"),
    ("Dallas",        "Dallas",        "US", "concert"),
    # ── global nightlife capitals ──
    ("Ibiza",         "Ibiza",         "ES", "club"),
    ("Barcelona",     "Barcelona",     "ES", "club"),
    ("London",        "London",        "GB", "club"),
    ("Manchester",    "Manchester",    "GB", "club"),
    ("Berlin",        "Berlin",        "DE", "club"),
    ("Amsterdam",     "Amsterdam",     "NL", "club"),
    ("Paris",         "Paris",         "FR", "concert"),
    ("Tokyo",         "Tokyo",         "JP", "club"),
    ("Sydney",        "Sydney",        "AU", "concert"),
    ("Toronto",       "Toronto",       "CA", "concert"),
    ("Mexico City",   "Mexico City",   "MX", "concert"),
    ("Sao Paulo",     "Sao Paulo",     "BR", "concert"),
]

def harvest_global_events():
    """Return a list of event dicts from Ticketmaster. NEVER raises; [] on any problem."""
    if not TM_KEY:
        print("  [TM] no TICKETMASTER_API_KEY set - skipping global events (Vegas only)")
        return []
    out, seen = [], set()
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    end   = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + TM_DAYS_AHEAD*86400))
    for label, city, cc, etype in TM_MARKETS:
        try:
            q = urllib.parse.urlencode({
                "apikey": TM_KEY, "city": city, "countryCode": cc,
                "classificationName": "music", "size": str(TM_PER_MARKET),
                "sort": "date,asc", "startDateTime": start, "endDateTime": end,
            })
            req = urllib.request.Request(TM_API + "?" + q, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            for ev in (data.get("_embedded", {}) or {}).get("events", []) or []:
                try:
                    name = (ev.get("name") or "").strip()
                    dates = ((ev.get("dates") or {}).get("start") or {})
                    iso = dates.get("dateTime") or dates.get("localDate")
                    if not name or not iso:
                        continue
                    if len(iso) == 10:
                        ts = _cal.timegm(time.strptime(iso, "%Y-%m-%d")) + 20*3600
                        datestr = iso
                    else:
                        ts = _cal.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
                        datestr = iso[:10]
                    venues = ((ev.get("_embedded") or {}).get("venues") or [{}])
                    venue = (venues[0].get("name") or label).strip()
                    key = (name.lower(), datestr, venue.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"artist": name, "venue": venue, "type": etype,
                                "city": label, "date": datestr, "ts": int(ts),
                                "url": ev.get("url") or ""})
                except Exception:
                    continue
        except Exception as e:
            print(f"  [TM] {label}: {e}")
            continue
    print(f"  [TM] harvested {len(out)} global events across {len(TM_MARKETS)} markets")
    return out


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

# concerts.vegas per-venue pages — every major Vegas concert/arena/stadium/theater
# venue. Same slug-based approach as No Cover (date+artist live in the event URL);
# the venue + type come from this config, so it survives layout changes. Adding a
# venue is one line. Each source is fetched independently (try/except) so one
# failing calendar never takes down the rest — that's the "overlay" redundancy.
VG_CV_SOURCES = [
    ("https://concerts.vegas/venue/msg-sphere-las-vegas/", "Sphere", "sphere"),
    ("https://concerts.vegas/venue/t-mobile-arena-events/", "T-Mobile Arena", "arena"),
    ("https://concerts.vegas/venue/allegiant-stadium-events/", "Allegiant Stadium", "stadium"),
    ("https://concerts.vegas/venue/the-colosseum-at-caesars-palace-events/", "The Colosseum at Caesars Palace", "concert"),
    ("https://concerts.vegas/venue/park-theater-at-park-mgm-events/", "Dolby Live at Park MGM", "concert"),
    ("https://concerts.vegas/venue/dolby-live-at-park-mgm-tickets/", "Dolby Live at Park MGM", "concert"),
    ("https://concerts.vegas/venue/mgm-grand-garden-arena-events/", "MGM Grand Garden Arena", "arena"),
    ("https://concerts.vegas/venue/michelob-ultra-arena-events/", "Michelob Ultra Arena", "arena"),
    ("https://concerts.vegas/venue/the-theater-at-virgin-hotels-las-vegas-events/", "The Theater at Virgin Hotels", "concert"),
    ("https://concerts.vegas/venue/24-oxford-at-virgin-hotels-las-vegas/", "24 Oxford at Virgin Hotels", "concert"),
    ("https://concerts.vegas/venue/resorts-world-theatre/", "Resorts World Theatre", "concert"),
    ("https://concerts.vegas/venue/bakkt-theater-at-planet-hollywood/", "Bakkt Theater at Planet Hollywood", "concert"),
    ("https://concerts.vegas/venue/house-of-blues-las-vegas/", "House of Blues", "concert"),
    ("https://concerts.vegas/venue/encore-theater-at-wynn-las-vegas/", "Encore Theater at Wynn", "concert"),
    ("https://concerts.vegas/venue/bleaulive-theater-at-fontainebleau/", "BleauLive Theater at Fontainebleau", "concert"),
    ("https://concerts.vegas/venue/brooklyn-bowl-las-vegas/", "Brooklyn Bowl", "concert"),
    ("https://concerts.vegas/venue/pearl-concert-theater-at-palms/", "Pearl Theater at Palms", "concert"),
    ("https://concerts.vegas/sports/", "Las Vegas", "sports"),
]
# Optional universal JSON-LD sources (schema.org Event). Point at ANY venue's
# official events page; the parser reads name/date/venue/tickets automatically.
VG_JSONLD_SOURCES = [
    # ("https://www.thesphere.com/calendar", "Sphere", "sphere"),
]
_CV_EVENT_RE = re.compile(r"https://concerts\.vegas/event/[a-z0-9\-]+/?")
_CV_DATE_RE = re.compile(r"-(%s)-([a-z]+)-(\d{1,2})-(\d{4})" % "|".join(_VG_WD))
_CV_CITIES = ["north-las-vegas", "las-vegas", "henderson", "paradise", "enterprise", "summerlin"]
_CV_SPORTS = ("vs", "nhl", "nba", "nfl", "ufc", "wnba", "golden-knights", "raiders", "aces", "stanley-cup", "playoff")
_CV_PER_SRC_MAX = 60   # bound per page so footer "more events" cross-links can't flood

def _cv_parse(url, venue, vtype):
    slug = url.rstrip("/").split("/event/")[-1]
    m = _CV_DATE_RE.search(slug)
    if not m:
        return None
    _wd, mon, day, year = m.groups()
    if mon not in _VG_MONTHS:
        return None
    head = slug[:m.start()]            # "<artist>-<city>"
    raw_head = head
    city = "Las Vegas"
    for c in _CV_CITIES:
        if head.endswith("-" + c):
            head = head[:-(len(c) + 1)]
            city = " ".join(w.capitalize() for w in c.split("-"))
            break
    if not head:
        return None
    t = vtype
    if any(k in raw_head for k in _CV_SPORTS):
        t = "sports"
    artist = " ".join(w.capitalize() for w in head.split("-"))
    ts = _cal.timegm((int(year), _VG_MONTHS[mon], int(day), 20, 0, 0, 0, 0, 0))
    return {"artist": artist, "venue": venue, "type": t, "city": city,
            "date": "%04d-%02d-%02d" % (int(year), _VG_MONTHS[mon], int(day)),
            "ts": ts, "url": url}

import html as _htmlmod
_LD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)

def _jsonld_events(page, default_venue, default_type):
    """Universal schema.org Event extractor — works on most venue/ticketing pages."""
    out = []
    for blk in _LD_RE.finditer(page):
        txt = _htmlmod.unescape(blk.group(1).strip())
        try:
            data = json.loads(txt)
        except Exception:
            continue
        if isinstance(data, dict):
            items = data.get("@graph") if isinstance(data.get("@graph"), list) else [data]
        elif isinstance(data, list):
            items = data
        else:
            items = []
        for it in items:
            if not isinstance(it, dict):
                continue
            typ = it.get("@type", "")
            if isinstance(typ, list):
                typ = typ[0] if typ else ""
            if "Event" not in str(typ):
                continue
            name, start = it.get("name"), it.get("startDate")
            if not name or not start:
                continue
            try:
                d = str(start)[:10]
                y, mo, da = (int(x) for x in d.split("-"))
                ts = _cal.timegm((y, mo, da, 20, 0, 0, 0, 0, 0))
            except Exception:
                continue
            loc = it.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            venue = (loc.get("name") if isinstance(loc, dict) else None) or default_venue
            url = it.get("url") or ""
            offers = it.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict) and offers.get("url"):
                url = offers["url"]
            out.append({"artist": str(name)[:80], "venue": venue, "type": default_type,
                        "city": "Las Vegas", "date": d, "ts": ts, "url": url or default_venue})
    return out


def scrape_vegas():
    """Aggregate Vegas events from many calendars. Each source is isolated so a
    single failure can't break the feed; results are merged + de-duped."""
    found = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PartyPortalBot/2.7)"}

    def _fetch(u):
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            return r.read().decode("utf-8", "ignore")

    # 1) No Cover nightclubs + dayclubs (slug parser)
    for cal_url in VG_CALENDARS:
        try:
            html = _fetch(cal_url)
        except Exception as e:
            print(f"  [VG WARN] {cal_url}: {e}")
            continue
        for m in _VG_EVENT_RE.finditer(html):
            ev = _vg_parse(m.group(0))
            if ev:
                found[(ev["artist"], ev["venue"], ev["date"])] = ev

    # 2) concerts.vegas per-venue pages (concerts, arenas, stadium, sphere, sports)
    for url, venue, vtype in VG_CV_SOURCES:
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  [CV WARN] {url}: {e}")
            continue
        n = 0
        seen_urls = set()
        for m in _CV_EVENT_RE.finditer(html):
            eu = m.group(0)
            if eu in seen_urls:
                continue
            seen_urls.add(eu)
            ev = _cv_parse(eu, venue, vtype)
            if ev:
                found[(ev["artist"], ev["venue"], ev["date"])] = ev
                n += 1
                if n >= _CV_PER_SRC_MAX:
                    break

    # 3) optional JSON-LD venue sources (universal / future-proof)
    for url, venue, vtype in VG_JSONLD_SOURCES:
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  [LD WARN] {url}: {e}")
            continue
        for ev in _jsonld_events(html, venue, vtype):
            found[(ev["artist"], ev["venue"], ev["date"])] = ev

    cutoff = int(time.time()) - 36 * 3600
    return sorted([e for e in found.values() if e["ts"] >= cutoff], key=lambda x: x["ts"])[:300]

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
        # Widen the horizon well beyond Las Vegas (no-op without an API key).
        try:
            vg = vg + harvest_global_events()
        except Exception as _ge:
            print(f"  [TM ERROR] {_ge} - keeping Vegas-only events")
        # Drop anything already finished, de-dupe, and sort soonest-first so the
        # calendar rolls forward on its own and never stalls on stale entries.
        _now_ts = int(time.time())
        _seen, _clean = set(), []
        for _e in sorted(vg, key=lambda x: x.get("ts", 0)):
            if _e.get("ts", 0) < _now_ts - 43200:      # >12h past = expired
                continue
            _k = (str(_e.get("artist","")).lower(), _e.get("date",""), str(_e.get("venue","")).lower())
            if _k in _seen:
                continue
            _seen.add(_k); _clean.append(_e)
        vg = _clean
        if len(vg) >= 8:
            with open("events.json", "w", encoding="utf-8") as f:
                json.dump({"updated": int(time.time()), "events": vg}, f, ensure_ascii=False, indent=2)
            print(f"[OK] events.json written — {len(vg)} Vegas events")
        else:
            print(f"[VG] only {len(vg)} events parsed — keeping existing events.json (no overwrite)")
    except Exception as e:
        print(f"[VG ERROR] {e} — events.json left unchanged")
    print("[Done]")
