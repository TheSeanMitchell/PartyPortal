#!/usr/bin/env python3
"""
PARTY PORTAL — Content Bot 3.0  (real news + a worldwide party calendar)
========================================================================
Runs on GitHub Actions 3x/day. Writes two files the page reads at runtime:

  feed.json    real party-culture headlines from ~120 music, nightlife, fashion
               and culture outlets (Google News site: feeds) plus topic feeds,
               sorted into 12 tabs.
  events.json  "On The Horizon": a curated list of the big festivals with their
               announced dates, plus club / dayclub / concert listings scraped
               from Las Vegas, Miami, Los Angeles, New York, London and more.

Quality rules (NUZU lineage):
  - site:<domain> queries pull straight from trusted press
  - trailing " - Source Name" stripped from every display title
  - junk + promo filter (ticket-resale and "how to watch" service posts, promo
    codes, betting, horoscopes, puzzle answers, shopping deals, press-release wires)
  - party-positive blocklist (no crime, politics, deaths, court cases)
  - broad outlets must match a short party keyword; specialist outlets pass on-topic
  - trust tiers (1 = specialist/major, 2 = solid, 3 = unrated) drive the dot colour
  - NOTHING is invented: if nothing real passes, the old file is left as it was.

Run locally:  python bot.py    (Python 3.8+, standard library only)
"""

import os, re, json, time, hashlib, html as htmllib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET
import urllib.request, urllib.parse, urllib.error
import calendar as _cal

# ───────────────────────────── CONFIG ─────────────────────────────
MAX_ITEMS      = 140
PER_SOURCE_MAX = 4      # max stories per outlet PER DAY (diversity, both days)
PER_DAY_MAX    = 70     # max stories kept per calendar day
BREAKING_HOURS = 36     # < 36h old  → "hot"
DAILY_HOURS    = 50     # < 50h old  → kept (today + yesterday, with margin)
FETCH_TIMEOUT  = 12
MAX_WORKERS    = 12
MIN_TITLE_LEN  = 28
MAX_TITLE_LEN  = 200
UA = "Mozilla/5.0 (compatible; PartyPortalBot/3.0; +https://theseanmitchell.github.io/PartyPortal/)"

# ──────────────────────── PARTY-CULTURE KEYWORDS ───────────────────
# Relevance gate for broad outlets. 2.x phrase list kept, plus (3.0) short,
# high-signal words: long phrases rarely appear in real headlines (NUZU 2.3 lesson,
# measured again for Party Portal with tools/pp_kw_gaps.py).
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
# ── 3.0: short, high-signal words (each one checked against real recorded headlines) ──
RAW_KEYWORDS += [
    "dj","djs","fest","lineup","line-up","headliner","headliners","headlines","presale","sold out","sells out",
    "tour","tours","concert","concerts","gig","gigs","setlist","encore","stage","live set","b2b",
    "rave","raves","raver","club","clubs","clubbing","party","parties","nye","new year's eve","halloween",
    "techno","house","trance","dnb","drum & bass","bass","dubstep","garage","disco","electronic","dance",
    "remix","edit","banger","anthem","single","album","ep","mixtape","debut","premiere","b-side",
    "rock","metal","punk","emo","grunge","band","bands","frontman","guitarist","drummer","reunion",
    "hip-hop","hip hop","rap","rapper","rappers","r&b","reggaeton","latin","afrobeats","k-pop",
    "runway","catwalk","swimwear","swimsuit","bikini","couture","fashion","designer","models","met gala",
    "victoria's secret","si swimsuit","miami swim week",
    "vegas","las vegas","sphere","ibiza","mykonos","tulum",
    "throwback","nostalgia","80s","90s","2000s","y2k","anniversary","retro","iconic",
    "residency","stadium","arena","amphitheatre","grammy","grammys","vmas","billboard hot 100","chart",
    # measured gaps (pp_kw_gaps.py, 7 Nov recording): retro music stories and runway weeks
    "song","songs","hit","hits","lyric","lyrics","riff","riffs","albums","the beatles","beatles","led zeppelin",
    "fleetwood mac","bowie","freddie mercury","ozzfest","riot fest","1960s","1970s","1980s","1990s",
    "runway show","fashion show","pre-fall","spring 2027","fall 2027","resort 2027","ss27","fw27",
    "creative director","chanel","dior","balenciaga","versace","gucci","prada","louis vuitton","saint laurent",
    "rabanne","mugler","jacquemus","skims","supermodel","supermodels",
]
KEYWORDS = set(k.lower() for k in RAW_KEYWORDS)

def make_pattern(words):
    esc = [re.escape(w) for w in sorted(words, key=len, reverse=True)]
    return re.compile(r'(?<![A-Za-z0-9])(?:' + '|'.join(esc) + r')(?![A-Za-z0-9])', re.IGNORECASE) if esc else None

KEYWORD_PAT = make_pattern(KEYWORDS)

# keep the feed party-positive (drop hard news / negativity)
BLOCKLIST = {
    "war","bombing","missile","airstrike","massacre","genocide","terrorist","terror attack",
    "shooting","stabbing","murder","killed","death toll","manslaughter","overdose death",
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
    # 3.0 additions (seen in recorded feeds)
    "dies","died","deaths","dead at","tribute to the late","remembering","in memoriam",
    "lawsuit","sued","charged with","charges filed","jail","jailed","court case","cops","injured",
    "trump","biden","vance","harris campaign","tariff","tariffs","ice raid","protest","protesters",
    # 3.2 additions: the wider net (topic searches) brings sport "World Tours" and TV shows
    "atp","wta","tennis","grand slam","short track","speed skating","figure skating","gold medal",
    "olympic","olympics","nhl","mlb","ncaa","pga","lpga","golf","cricket","rugby",
    "premier league","champions league","la liga","serie a","bundesliga","semifinal","semi-final",
    "quarterfinal","quarter-final","playoffs","touchdown","quarterback","boxing match",
    "cast revealed","series cast","tv series","zombie","season finale","box office",
}
BLOCK_PAT = make_pattern(BLOCKLIST)

# ══════════════════════ PROMO / JUNK FILTER (3.0, ported from NUZU 2.3) ══════════════════════
# Advertising and "service" posts are not news. Each rule names a reason; the build log
# prints the counts so a wrong removal is easy to spot. Calibrated on the 7 Nov 2026
# recording with tools/promo_calibrate.py (every removal read by hand).
_PP_PROMO_RULES = [
    ("promo code", r"\b(promo|bonus|coupon|discount|referral|offer|signup|sign-up|presale) codes?\b"),
    ("promo code", r"\bbonus bets?\b|\bfree spins?\b|\bno[- ]deposit\b|\bsign[- ]?up (bonus|offer|promo)\b"),
    ("sportsbook promo", r"\b(betmgm|draftkings|fanduel|caesars sportsbook|bet365|fanatics sportsbook|espn ?bet|hard rock bet|betrivers|prizepicks|underdog fantasy)\b.{0,60}\b(code|bonus|promo|offer|boost)\b"),
    ("betting", r"\b(best bets?|betting (picks|odds|preview|tips|lines|guide)|player props?|prop bets?|parlays?|odds to (win|perform)|halftime show odds|grammy odds|betting favorite)\b"),
    ("ticket resale", r"\b(cheap(est)?|discount(ed)?|last[- ]minute|resale|secondary[- ]market) tickets?\b|\btickets? (are |now )?(starting|start|from) (at )?\$\d"),
    ("ticket how-to", r"\bhow (to|can (i|you)) (buy|get|score|find|cop) .{0,40}tickets?\b|\bwhere to (buy|get|find|shop( for)?) .{0,40}tickets?\b|\btickets?:? (prices?|price guide|how to)\b|\bhow much (are|do|does) .{0,40}tickets?\b"),
    ("how to watch", r"\b(how|where) to (watch|stream|livestream|listen)\b|\blive ?stream(ing)? (free|online|link)\b|\b(tv channel|start time),? (live stream|how to watch|streaming)\b"),
    ("shopping", r"\b(best (deals?|buys?)|deals? of the (day|week)|black friday (deals?|sales?)|cyber monday (deals?|sales?)|prime (big )?(deal )?day|gift (guide|ideas)|shop (now|the sale|our)|lowest price|price drop|\d+% off\b|save (up to )?\$\d[\d,]*|under \$\d+\b|we tried|tested and reviewed|our (favorite|editors'?) picks)\b"),
    ("shopping", r"\b(\d+|the) best .{1,40} (to buy|you can buy|for (the )?money|on amazon|at (nordstrom|target|walmart|revolve|amazon))\b|\bbest .{1,30} (of|for) 20\d\d,? (tested|reviewed|ranked)\b|\bon amazon\b.{0,30}\b(deal|sale|discount)\b"),
    ("puzzle answers", r"\b(wordle|quordle|connections|strands|spelling bee|crossword|sudoku|nyt (mini|connections|strands))\b.{0,50}\b(answers?|hints?|solutions?|clues?)\b|\bhints? and answers?\b"),
    ("horoscope", r"\b(horoscopes?|tarot|zodiac signs?|astrology|mercury retrograde)\b"),
    ("lottery", r"\b(winning numbers|lottery results|powerball|mega millions)\b"),
    ("sponsored", r"\b(sponsored( content| post| by)?|paid (content|post|partnership)|advertorial|partner content|brandvoice)\b"),
    ("quiz / poll", r"\b(take (the|our) quiz|quiz:|which .{1,30} are you\b|vote (now|for your)|reader poll|poll:)\b"),
]
_PP_PROMO_RES = [(why, re.compile(p, re.I)) for why, p in _PP_PROMO_RULES]
_PP_PROMO_SOURCES = re.compile(
    r"\b(pr ?newswire|globe ?newswire|business ?wire|access ?newswire|accesswire|ein ?presswire|"
    r"newswire\.com|24-7 ?press ?release|openpr|issuewire|pr\.com|prweb|newsfile|send2press|"
    r"prlog|newswires|stock titan|marketbeat|motley fool|zacks|sportsbook ?review|covers\.com|"
    r"action network|oddschecker|odds shark|pickswise|ticketsmarter|vivid seats|stubhub|seatgeek|"
    r"tickpick|gametime|ticketnetwork|ticket ?club|cheaptickets|ticketcity|scorebig)\b", re.I)


_PP_NEWS_VERB = re.compile(r"\b(adds?|added|announces?|announced|extends?|reveals?|revealed|confirms?|confirmed|returns?|"
                           r"expands?|launch(es)?|begins?|opens?|plummets?|soars?|headlines?|headlining)\b", re.I)   # 3.2: + ticket news


def why_promo(raw_title, source=""):
    """The reason an item is advertising / non-news, or None if it is news."""
    t = raw_title or ""
    for why, rx in _PP_PROMO_RES:
        if rx.search(t):
            if why == "ticket how-to" and _PP_NEWS_VERB.search(t.split(":")[0]):
                continue      # "X adds 2027 dates: here's how to buy tickets" is news first
            return why
    if source and _PP_PROMO_SOURCES.search(source):
        return "promo publisher"
    tail = t.rsplit(" - ", 1)[-1] if " - " in t else ""
    if tail and _PP_PROMO_SOURCES.search(tail):
        return "promo publisher"
    return None


_PP_PROMO_LOG = {}

# 3.2: outlets the topic searches bring in that are not party press - copy-paste sites (they
# inflate a story's outlet count) and a film/TV database. Seen in the 21 Nov recording.
_PP_SKIP_SRC = re.compile(r"(\.co\.id|\.id)$|^(suaragarut|limapagi|bsinews|peradaban|demokratis)\b|"
                          r"^vietnam\.vn$|\bimdb\b", re.I)

# ───────────────────── SOURCE TRUST + FRIENDLY NAMES ───────────────
TIER1 = {  # specialist EDM/dance press + major outlets
    "mixmag","dj mag","djmag","resident advisor","ra","edm.com","dancing astronaut",
    "billboard","rolling stone","pitchfork","nme","variety","stereogum","consequence",
    "the guardian","bbc","npr","associated press","ap news","reuters","time out",
    "vogue","wwd","women's wear daily","harper's bazaar","elle","the cut","the face","dazed",
    "loudwire","kerrang","xxl","complex","hiphopdx","pollstar","iq magazine","las vegas review-journal",
    "xlr8r","fact","electronic beats","beatportal","spin","the new york times","los angeles times",
}
TIER2 = {  # solid music/culture blogs & city press
    "edmtunes","your edm","we rave you","6am","magnetic magazine","magnetic mag",
    "electronic groove","edm identity","festicket","ticketnews",
    "vegas weekly","las vegas weekly","timeout","attack magazine","mixdown",
    "the line of best fit","clash","diy magazine","brooklyn vegan","brooklynvegan","paper magazine","paper",
    "edm sauce","data transmission","decoded magazine","when we dip","mixmag asia","dj times",
    "the nocturnal times","ravejungle","rave jungle","run the trap","ultimate classic rock",
    "revolver","metal injection","hotnewhiphop","rap-up","vibe","revolt","okayplayer","uproxx",
    "edm maniac","music festival wizard","ibiza spotlight","electronic vegas",
    "louder","loudersound","blabbermouth","alternative press","rock sound","the prp",
    "the source","hip-hop wired","hiphopwired","entertainment weekly","ew.com","jambase",
    "live for live music","efestivals","festival insights","digital music news",
    "fashionista","hypebeast","highsnobiety","business of fashion","the business of fashion",
    "far out magazine","far out","i-d","vice","mtv","inverted audio","5 magazine","earmilk",
    "dance music nw","edm house network","electronic midwest","1001tracklists","insomniac",
    "vital vegas","las vegas sun","fox5 vegas","8 news now","8newsnow","ktnv","miami new times",
    "la weekly","secret nyc","secret los angeles","secret miami","majorca daily bulletin",
    "mexico news daily","the rio times","rio times","sports illustrated swimsuit","si swimsuit",
    "greek reporter","euro weekly news","bangkok post","paste","paste music","exclaim","exclaim!","the fader",
    "music week","remezcla","allhiphop","hiphop-n-more","rolling out","diy",
}
NICHE_SOURCES = {  # accepted on-topic even without a keyword hit
    "mixmag","dj mag","djmag","resident advisor","edm.com","dancing astronaut","edmtunes",
    "your edm","we rave you","6am","magnetic magazine","magnetic mag","electronic groove",
    "edm identity","attack magazine","ra","edm sauce","data transmission","decoded magazine",
    "when we dip","mixmag asia","dj times","the nocturnal times","ravejungle","rave jungle","run the trap",
    "edm maniac","ibiza spotlight","electronic vegas","xlr8r","beatportal","electronic beats",
    "inverted audio","5 magazine","dance music nw","edm house network","electronic midwest",
    "1001tracklists","insomniac","music festival wizard","efestivals","festival insights",
    "jambase","live for live music","vital vegas","las vegas weekly","sports illustrated swimsuit",
    "si swimsuit","loudwire","kerrang","revolver","metal injection","blabbermouth","rock sound",
    "alternative press","hiphopdx","xxl","hotnewhiphop","rap-up","hip-hop wired","hiphopwired",
}

def _name_has(n, s):
    # whole-word match, so "ra" (Resident Advisor) never matches inside "Libra" (NUZU 2.3 fix)
    return re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", n) is not None

def source_tier(name):
    n = (name or "").lower()
    if any(_name_has(n, s) for s in TIER1): return 1
    if any(_name_has(n, s) for s in TIER2): return 2
    return 3

def is_niche(name):
    n = (name or "").lower()
    return any(_name_has(n, s) for s in NICHE_SOURCES)

# ─────────────────────────── NEWS TABS ───────────────────────────
# Order matters: the first tab whose keywords match a headline wins; if none
# match, the story goes to its source's home tab.
TAB_ORDER = ["Las Vegas", "Tickets & Lineups", "Fashion & Swim", "Ibiza & Global", "Festivals", "Hip-Hop", "Rock",
             "Retro & Culture", "Techno & House", "EDM & Dance", "Nightlife & Clubs", "Pop & Tours"]
RAW_TAB_KEYWORDS = {
    "Las Vegas": ["vegas","las vegas","sphere","the strip","wynn","encore beach","encore las vegas","zouk","omnia","xs nightclub","hakkasan",
                  "marquee nightclub","marquee dayclub","tao","drai's","fontainebleau las vegas","resorts world","caesars","mgm grand","allegiant",
                  "t-mobile arena","cosmopolitan","palms casino","circa resort","fremont","dolby live","colosseum at caesars","wet republic",
                  "liv beach","ayu dayclub","jewel nightclub","on the record","area15","f1 las vegas"],
    "Ibiza & Global": ["ibiza","mykonos","tulum","berlin","berghain","amsterdam","ade","tokyo","seoul","bangkok","bali",
                       "dubai","rio","brazil","brasil","mexico city","cancun","cancún","croatia","hvar","ayia napa",
                       "magaluf","mallorca","majorca","goa","carnival","carnaval","notting hill","full moon party",
                       "ushuaia","ushuaïa","pacha","amnesia","dc10","dc-10","hï ibiza","hi ibiza","o beach","tenerife",
                       "benidorm","barcelona","lisbon","cape town","johannesburg","lagos","sydney","melbourne",
                       "singapore","beirut","tbilisi","bassiani","printworks","fabric london"],
    "Tickets & Lineups": ["lineup","line-up","line up","presale","pre-sale","on sale","sold out","sells out","sell out",
                          "set times","phase 1","phase one","first wave","second wave","announces lineup","lineup revealed",
                          "tickets","ticket","waitlist","early bird","ga+","vip passes","passes"],
    "Festivals": ["festival","festivals","fest","coachella","edc","electric daisy","tomorrowland","ultra music","ultra miami","ultra europe","umf","glastonbury",
                  "lollapalooza","lolla","bonnaroo","burning man","creamfields","rolling loud","sziget","untold","primavera",
                  "sonar","sónar","defqon","mysteryland","awakenings","lost lands","electric forest","outside lands",
                  "governors ball","gov ball","iii points","movement festival","movement detroit","hard summer","beyond wonderland","day trip",
                  "portola","north coast","dreamstate","nocturnal wonderland","escape halloween","countdown nye","ozora",
                  "boom festival","wireless festival","reading festival","reading & leeds","download festival","rock in rio","riot fest","ozzfest","splendour","fuji rock","exit festival",
                  "dekmantel","time warp","parookaville","zamna","day zero","shambhala","holy ship","lightning in a bottle",
                  "bumbershoot","austin city limits","acl","osheaga","bottlerock","shaky knees","firefly","summerfest"],
    "Hip-Hop": ["hip hop","hip-hop","rap","rapper","rappers","drake","travis scott","kendrick","j. cole","j cole","cardi b",
                "nicki minaj","megan thee stallion","21 savage","playboi carti","lil wayne","lil baby","lil uzi",
                "lil durk","eminem","snoop","50 cent","jay-z","kanye","tyler, the creator","tyler the creator","a$ap",
                "asap rocky","don toliver","metro boomin","central cee","doja cat","gunna","young thug","quavo",
                "post malone","ice spice","glorilla","sexyy red","lil yachty","jid","denzel curry","freestyle","mixtape","grime"],
    "Rock": ["rock","metal","punk","emo","grunge","hardcore","guitarist","frontman","drummer","riff","metallica",
             "foo fighters","red hot chili peppers","rhcp","green day","guns n' roses","guns n roses","pearl jam",
             "rolling stones","ac/dc","iron maiden","slipknot","linkin park","arctic monkeys","blink-182",
             "paramore","my chemical romance","bring me the horizon","rammstein","the killers","kings of leon",
             "nirvana","oasis","bon jovi","aerosmith","def leppard","mötley crüe","motley crue","korn",
             "deftones","system of a down","avenged sevenfold","måneskin","maneskin","sum 41","the offspring",
             "weezer","queens of the stone age","the strokes","jack white","royal blood","greta van fleet","sleep token"],
    "Fashion & Swim": ["fashion","runway","catwalk","swim","swimsuit","swimwear","bikini","couture","vogue","met gala",
                       "fashion week","victoria's secret","victoria’s secret","si swimsuit","sports illustrated swimsuit",
                       "outfit","outfits","streetwear","designer","models","supermodel","lingerie","resort wear",
                       "dior","chanel","versace","prada","gucci","balenciaga","louis vuitton","mugler",
                       "jacquemus","skims","rave wear","festival fashion","pre-fall","spring 2027 collection","spring 2027 show",
                       "spring 2027 shows","fall 2027 collection","resort 2027","creative director","rabanne","saint laurent",
                       "supermodels","fashion show"],
    "Retro & Culture": ["mtv","vh1","trl","music video","retro","throwback","nostalgia","80s","90s","2000s","y2k",
                        "1960s","1970s","1980s","1990s","in 1965","in 1969","in 1971","in 1975","in 1977","in 1978",
                        "in 1979","in 1980","in 1982","in 1984","in 1985","in 1987","in 1989","in 1991","in 1994",
                        "in 1997","in 1999","beatles","led zeppelin","fleetwood mac","bowie","freddie mercury",
                        "anniversary","spring break","soul train","woodstock","live aid","documentary","biopic",
                        "club kid","rave culture","history of","iconic","classic album","remaster","reissue","turns 20",
                        "turns 25","turns 30","years ago","memoir","exhibition","museum","art basel","culture"],
    "Techno & House": ["techno","house music","tech house","deep house","afro house","amapiano","minimal techno",
                       "warehouse","boiler room","resident advisor","drumcode","afterlife","keinemusik","solomun","carl cox",
                       "charlotte de witte","amelie lens","adam beyer","peggy gou","black coffee","chris lake",
                       "john summit","dom dolla","mau p","hugel","vintage culture","tale of us","anyma","argy","artbat",
                       "adriatique","hot creations","jamie jones","defected","glitterbox","circoloco","dixon","ben böhmer",
                       "four tet","bicep","kerri chandler","honey dijon","folamour","purple disco machine","sara landry",
                       "i hate models","kettama","prospa","josh baker","skream","jamie xx","fred again","cercle"],
    "EDM & Dance": ["edm","dj","djs","dance music","electronic","rave","dubstep","bass","trance","hardstyle",
                    "drum and bass","drum & bass","dnb","psytrance","b2b","remix","tiësto","tiesto","martin garrix",
                    "david guetta","calvin harris","deadmau5","skrillex","diplo","marshmello","afrojack","armin van buuren",
                    "eric prydz","swedish house mafia","zedd","kygo","alesso","avicii","illenium","excision","subtronics",
                    "rl grime","odesza","above & beyond","alok","steve aoki","dimitri vegas","hardwell","dj snake",
                    "kaskade","gryffin","seven lions","porter robinson","madeon","flume","rüfüs","rufus du sol","insomniac"],
    "Nightlife & Clubs": ["nightlife","nightclub","nightclubs","club","clubs","clubbing","club night","party","parties",
                          "rooftop","rooftop bar","cocktail bar","lounge","dayclub","day club","pool party","beach club","after hours",
                          "afterparty","after-party","bottle service","speakeasy","opening night","nye","new year's eve",
                          "halloween","dance floor","dancefloor","venue","residency"],
    "Pop & Tours": ["tour","tours","world tour","concert","concerts","stadium","arena","setlist","live show","performs",
                    "performance","album","single","pop","taylor swift","beyoncé","beyonce","dua lipa","the weeknd",
                    "bad bunny","karol g","sabrina carpenter","chappell roan","charli xcx","olivia rodrigo","ariana grande",
                    "lady gaga","rihanna","bruno mars","coldplay","ed sheeran","billie eilish","harry styles","usher",
                    "shakira","kylie","madonna","backstreet boys","jonas brothers","grammy","grammys","billboard"],
}
TAB_PATS = {t: make_pattern(set(w.lower() for w in RAW_TAB_KEYWORDS[t])) for t in TAB_ORDER}

# ─────────────────────────── RSS SOURCES ───────────────────────────
def g(q):
    return "https://news.google.com/rss/search?q=" + q + "&hl=en-US&gl=US&ceid=US:en"

def site(domain, extra="", days=3):
    q = "site:" + domain + (("+" + extra) if extra else "") + "+when:%dd" % days
    return g(q)

# (display name, feed url, home tab). Specialist outlets: whole feed; broad outlets:
# the query itself narrows to party/music topics and the keyword gate does the rest.
NEWS_SOURCES = [
    # ── EDM & Dance press ──
    ("Mixmag",            site("mixmag.net"),                 "EDM & Dance"),
    ("DJ Mag",            site("djmag.com"),                  "EDM & Dance"),
    ("EDM.com",           site("edm.com"),                    "EDM & Dance"),
    ("Dancing Astronaut", site("dancingastronaut.com"),       "EDM & Dance"),
    ("Your EDM",          site("youredm.com"),                "EDM & Dance"),
    ("EDMTunes",          site("edmtunes.com"),               "EDM & Dance"),
    ("We Rave You",       site("weraveyou.com"),              "EDM & Dance"),
    ("Magnetic Magazine", site("magneticmag.com", days=4),    "EDM & Dance"),
    ("Electronic Groove", site("electronicgroove.com", days=4),"EDM & Dance"),
    ("EDM Identity",      site("edmidentity.com", days=4),    "EDM & Dance"),
    ("EDM Sauce",         site("edmsauce.com", days=4),       "EDM & Dance"),
    ("EDM Maniac",        site("edmmaniac.com", days=4),      "EDM & Dance"),
    ("The Nocturnal Times", "https://thenocturnaltimes.com/feed/", "EDM & Dance"),
    ("Dance Music NW",    "https://www.dancemusicnw.com/feed/", "EDM & Dance"),
    ("Rave Jungle",       site("ravejungle.com", days=4),     "EDM & Dance"),
    ("1001Tracklists",    site("1001tracklists.com", days=4), "EDM & Dance"),
    ("Insomniac",         site("insomniac.com", days=5),      "Festivals"),
    ("Mixmag Asia",       site("mixmag.asia", days=4),        "Ibiza & Global"),
    ("Beatportal",        site("beatportal.com", days=4),     "Techno & House"),
    ("EDM House Network", site("edmhousenetwork.com", days=5),"EDM & Dance"),
    ("Electronic Midwest",site("electronicmidwest.com", days=5),"EDM & Dance"),
    ("Earmilk",           site("earmilk.com", "dj+OR+festival+OR+tour+OR+remix+OR+edm", 4), "EDM & Dance"),
    # ── Techno & House ──
    ("Resident Advisor",  site("ra.co"),                      "Techno & House"),
    ("Attack Magazine",   site("attackmagazine.com", days=5), "Techno & House"),
    ("Data Transmission", site("datatransmission.co", days=5),"Techno & House"),
    ("Decoded Magazine",  site("decodedmagazine.com", days=5),"Techno & House"),
    ("When We Dip",       site("whenwedip.com", days=5),      "Techno & House"),
    ("Inverted Audio",    site("invertedaudio.com", days=5),  "Techno & House"),
    ("5 Magazine",        site("5mag.net", days=6),           "Techno & House"),
    ("Clash",             site("clashmusic.com", "dj+OR+festival+OR+club+OR+techno+OR+house+OR+tour", 4), "Techno & House"),
    # ── Festivals + Tickets & Lineups ──
    ("Music Festival Wizard", site("musicfestivalwizard.com", days=4), "Festivals"),
    ("Festival Insights", site("festivalinsights.com", days=5), "Festivals"),
    ("eFestivals",        site("efestivals.co.uk", days=5),   "Festivals"),
    ("IQ Magazine",       site("iqmagazine.com", "festival+OR+tour+OR+club+OR+nightlife", 4), "Festivals"),
    ("Pollstar",          site("pollstar.com", "festival+OR+tour+OR+residency", 4), "Pop & Tours"),
    ("JamBase",           site("jambase.com", days=4),        "Festivals"),
    ("Live For Live Music", site("liveforlivemusic.com", days=4), "Festivals"),
    ("Festivals",         g("music+festival+2027+OR+festival+lineup+OR+festival+headliner+when:2d"), "Festivals"),
    ("EDC / Ultra / Tomorrowland", g("electric+daisy+carnival+OR+EDC+OR+ultra+music+festival+OR+tomorrowland+when:3d"), "Festivals"),
    ("Coachella",         g("coachella+2027+OR+coachella+lineup+when:4d"), "Festivals"),
    ("Burning Man",       g("burning+man+OR+black+rock+city+when:5d"), "Festivals"),
    ("Creamfields / UK fests", g("creamfields+OR+glastonbury+2027+OR+reading+leeds+festival+when:4d"), "Festivals"),
    ("Lineups & Presales", g("lineup+announced+OR+presale+OR+%22phase+1%22+festival+when:3d"), "Tickets & Lineups"),
    ("Tour Announcements", g("announces+tour+2027+OR+world+tour+dates+OR+residency+dates+when:2d"), "Pop & Tours"),
    # ── Nightlife & Clubs ──
    ("Time Out Nightlife",g("site:timeout.com+nightlife+OR+club+OR+party+OR+rooftop+when:4d"), "Nightlife & Clubs"),
    ("Secret NYC",        site("secretnyc.co", "party+OR+club+OR+rooftop+OR+concert+OR+festival", 5), "Nightlife & Clubs"),
    ("Secret Los Angeles",site("secretlosangeles.com", "party+OR+club+OR+rooftop+OR+concert+OR+festival", 5), "Nightlife & Clubs"),
    ("Secret Miami",      site("secretmiami.com", "party+OR+club+OR+rooftop+OR+concert+OR+festival", 5), "Nightlife & Clubs"),
    ("Miami New Times",   site("miaminewtimes.com", "club+OR+dj+OR+party+OR+festival+OR+concert", 4), "Nightlife & Clubs"),
    ("LA Weekly",         site("laweekly.com", "club+OR+dj+OR+party+OR+festival+OR+concert", 5), "Nightlife & Clubs"),
    ("Nightlife",         g("nightlife+OR+nightclub+OR+%22club+night%22+when:2d"), "Nightlife & Clubs"),
    ("LA Nightlife",      g("los+angeles+nightlife+OR+hollywood+club+OR+la+warehouse+party+when:4d"), "Nightlife & Clubs"),
    ("NYC Nightlife",     g("brooklyn+mirage+OR+nyc+nightlife+OR+house+of+yes+OR+brooklyn+club+when:4d"), "Nightlife & Clubs"),
    ("Miami Nightlife",   g("miami+nightlife+OR+e11even+OR+club+space+miami+OR+liv+miami+when:4d"), "Nightlife & Clubs"),
    ("New Orleans",       g("bourbon+street+OR+new+orleans+nightlife+OR+mardi+gras+when:5d"), "Nightlife & Clubs"),
    # ── Las Vegas ──
    ("Las Vegas Review-Journal", site("reviewjournal.com", "nightlife+OR+concert+OR+residency+OR+sphere+OR+dj+OR+club", 3), "Las Vegas"),
    ("Las Vegas Weekly",  site("lasvegasweekly.com", days=5), "Las Vegas"),
    ("Vital Vegas",       "https://vitalvegas.com/feed/",     "Las Vegas"),
    ("Las Vegas Sun",     site("lasvegassun.com", "nightlife+OR+concert+OR+residency+OR+sphere+OR+club", 4), "Las Vegas"),
    ("FOX5 Vegas",        site("fox5vegas.com", "%22las+vegas%22+concert+OR+residency+OR+sphere+OR+nightclub+OR+dayclub", 4), "Las Vegas"),
    ("8 News Now",        site("8newsnow.com", "%22las+vegas%22+concert+OR+residency+OR+sphere+OR+nightclub+OR+dayclub", 4), "Las Vegas"),
    ("KTNV",              site("ktnv.com", "%22las+vegas%22+concert+OR+residency+OR+sphere+OR+nightclub+OR+dayclub", 4), "Las Vegas"),
    ("Vegas Party",       g("las+vegas+nightlife+OR+vegas+nightclub+OR+las+vegas+sphere+OR+vegas+residency+when:2d"), "Las Vegas"),
    ("Vegas Dayclubs",    g("las+vegas+pool+party+OR+vegas+dayclub+OR+encore+beach+club+when:5d"), "Las Vegas"),
    # ── Ibiza & Global party ──
    ("Ibiza Spotlight",   site("ibiza-spotlight.com", days=6),"Ibiza & Global"),
    ("Majorca Daily Bulletin", site("majorcadailybulletin.com", "ibiza+OR+club+OR+party+OR+dj+OR+festival", 6), "Ibiza & Global"),
    ("Mexico News Daily", site("mexiconewsdaily.com", "tulum+OR+festival+OR+concert+OR+party+OR+cancun", 6), "Ibiza & Global"),
    ("Greek Reporter",    site("greekreporter.com", "mykonos+OR+party+OR+festival+OR+concert", 7), "Ibiza & Global"),
    ("Euro Weekly News",  site("euroweeklynews.com", "ibiza+OR+festival+OR+party+OR+concert+OR+dj", 5), "Ibiza & Global"),
    ("Ibiza",             g("ibiza+club+OR+ibiza+season+OR+ushuaia+ibiza+OR+pacha+ibiza+when:5d"), "Ibiza & Global"),
    ("Tulum / Mexico",    g("tulum+party+OR+zamna+OR+day+zero+tulum+OR+edc+mexico+when:5d"), "Ibiza & Global"),
    ("Berlin / Amsterdam",g("berghain+OR+tresor+OR+berlin+techno+OR+amsterdam+dance+event+when:5d"), "Ibiza & Global"),
    ("London Clubbing",   g("fabric+london+OR+printworks+OR+london+nightlife+OR+ministry+of+sound+when:4d"), "Ibiza & Global"),
    ("Brazil / Carnival", g("rio+carnival+OR+carnaval+OR+rock+in+rio+OR+tomorrowland+brasil+when:5d"), "Ibiza & Global"),
    ("Asia Nightlife",    g("%22tokyo+nightlife%22+OR+%22seoul+nightlife%22+OR+%22bangkok+nightlife%22+OR+%22zouk+singapore%22+when:7d"), "Ibiza & Global"),
    ("Australia Scene",   g("sydney+nightlife+OR+melbourne+club+OR+australia+music+festival+when:5d"), "Ibiza & Global"),
    ("Amapiano / Afro",   g("amapiano+OR+afro+house+OR+afrobeats+festival+OR+afro+nation+when:4d"), "Techno & House"),
    ("Psytrance",         g("psytrance+festival+OR+ozora+OR+boom+festival+when:6d"), "EDM & Dance"),
    ("Hardstyle / DnB",   g("hardstyle+OR+defqon+OR+drum+and+bass+OR+hard+techno+when:4d"), "EDM & Dance"),
    # ── Rock ──
    ("Loudwire",          site("loudwire.com", "tour+OR+festival+OR+reunion+OR+concert+OR+live", 3), "Rock"),
    ("Ultimate Classic Rock", site("ultimateclassicrock.com", "tour+OR+festival+OR+residency+OR+live+OR+reunion", 4), "Rock"),
    ("Kerrang!",          site("kerrang.com", days=4),        "Rock"),
    ("Revolver",          site("revolvermag.com", days=5),    "Rock"),
    ("Metal Injection",   site("metalinjection.net", "tour+OR+festival+OR+live", 4), "Rock"),
    ("Louder",            site("loudersound.com", "tour+OR+festival+OR+live+OR+reunion", 4), "Rock"),
    ("Blabbermouth",      site("blabbermouth.net", "tour+OR+festival+OR+live+OR+reunion", 3), "Rock"),
    ("Alternative Press", site("altpress.com", days=5),       "Rock"),
    ("Rock Sound",        site("rocksound.tv", days=5),       "Rock"),
    ("The PRP",           site("theprp.com", "tour+OR+festival", 5), "Rock"),
    ("BrooklynVegan",     site("brooklynvegan.com", "festival+OR+tour+OR+lineup+OR+show", 3), "Rock"),
    ("Consequence",       site("consequence.net", "festival+OR+tour+OR+lineup+OR+rave+OR+concert", 2), "Rock"),
    ("Rock Tours",        g("rock+band+tour+2027+OR+stadium+tour+OR+reunion+tour+when:3d"), "Rock"),
    # ── Hip-Hop ──
    ("XXL",               site("xxlmag.com", days=3),         "Hip-Hop"),
    ("Complex Music",     site("complex.com", "rapper+OR+album+OR+tour+OR+festival", 3), "Hip-Hop"),
    ("HotNewHipHop",      site("hotnewhiphop.com", "tour+OR+festival+OR+concert+OR+album", 3), "Hip-Hop"),
    ("Rap-Up",            site("rap-up.com", days=4),         "Hip-Hop"),
    ("The Source",        site("thesource.com", days=4),      "Hip-Hop"),
    ("Vibe",              site("vibe.com", "music+OR+tour+OR+festival+OR+album", 4), "Hip-Hop"),
    ("Revolt",            site("revolt.tv", "music+OR+tour+OR+festival+OR+album", 4), "Hip-Hop"),
    ("Hip-Hop Wired",     site("hiphopwired.com", "tour+OR+festival+OR+concert+OR+album", 4), "Hip-Hop"),
    ("AllHipHop",         site("allhiphop.com", "tour+OR+festival+OR+concert+OR+album", 3), "Hip-Hop"),
    ("HipHop-N-More",     site("hiphop-n-more.com", days=5),  "Hip-Hop"),
    ("Rolling Out",       site("rollingout.com", "concert+OR+tour+OR+festival+OR+album", 3), "Hip-Hop"),
    ("Uproxx Music",      site("uproxx.com", "rapper+OR+album+OR+tour+OR+festival+OR+concert", 4), "Hip-Hop"),
    ("Rolling Loud / Rap Live", g("rolling+loud+OR+rap+concert+OR+hip+hop+festival+OR+rap+residency+when:4d"), "Hip-Hop"),
    # ── Pop & Tours (broad music press) ──
    ("Billboard",         site("billboard.com", "tour+OR+festival+OR+dance+OR+electronic+OR+concert", 2), "Pop & Tours"),
    ("Rolling Stone",     site("rollingstone.com", "festival+OR+electronic+OR+dj+OR+tour+OR+concert", 2), "Pop & Tours"),
    ("Variety Music",     site("variety.com", "tour+OR+festival+OR+concert+OR+residency", 3), "Pop & Tours"),
    ("Pitchfork",         site("pitchfork.com", "festival+OR+electronic+OR+tour", 3), "Pop & Tours"),
    ("NME",               site("nme.com", "festival+OR+dance+OR+tour+OR+gig", 3), "Pop & Tours"),
    ("Stereogum",         site("stereogum.com", "tour+OR+festival+OR+live", 3), "Pop & Tours"),
    ("SPIN",              "https://www.spin.com/feed/",        "Pop & Tours"),
    ("Paste Music",       site("pastemagazine.com", "festival+OR+tour+OR+live+OR+concert", 3), "Pop & Tours"),
    ("The Line of Best Fit", site("thelineofbestfit.com", "festival+OR+tour+OR+live", 4), "Pop & Tours"),
    ("DIY",               site("diymag.com", "festival+OR+tour+OR+live", 5), "Rock"),
    ("Exclaim!",          site("exclaim.ca", "festival+OR+tour+OR+concert+OR+dj", 3), "Pop & Tours"),
    ("The FADER",         site("thefader.com", days=4),       "Hip-Hop"),
    ("Music Week",        site("musicweek.com", "festival+OR+tour+OR+live+OR+club", 4), "Pop & Tours"),
    ("The Guardian Music",site("theguardian.com/music", "festival+OR+tour+OR+club+OR+rave+OR+gig", 3), "Pop & Tours"),
    ("Remezcla",          site("remezcla.com", days=5),       "Ibiza & Global"),
    ("Entertainment Weekly", site("ew.com", "tour+OR+concert+OR+festival+OR+music", 3), "Pop & Tours"),
    ("Digital Music News",site("digitalmusicnews.com", "tour+OR+festival+OR+tickets+OR+concert", 4), "Pop & Tours"),
    ("DJ Tours",          g("dj+residency+OR+dj+tour+2027+OR+b2b+set+when:3d"), "EDM & Dance"),
    # ── Fashion & Swim ──
    ("Vogue",             site("vogue.com", "runway+OR+fashion+week+OR+swim+OR+festival+OR+party", 3), "Fashion & Swim"),
    ("WWD",               site("wwd.com", "runway+OR+fashion+week+OR+swim+OR+show", 3), "Fashion & Swim"),
    ("Harper's Bazaar",   site("harpersbazaar.com", "runway+OR+fashion+week+OR+swim+OR+party", 4), "Fashion & Swim"),
    ("ELLE",              site("elle.com", "runway+OR+fashion+week+OR+swim+OR+party", 4), "Fashion & Swim"),
    ("Fashionista",       site("fashionista.com", days=5),    "Fashion & Swim"),
    ("The Cut",           site("thecut.com", "fashion+OR+runway+OR+party+OR+nightlife", 5), "Fashion & Swim"),
    ("Hypebeast",         site("hypebeast.com", "fashion+OR+music+OR+festival+OR+runway", 4), "Fashion & Swim"),
    ("Highsnobiety",      site("highsnobiety.com", "fashion+OR+music+OR+party+OR+runway", 5), "Fashion & Swim"),
    ("Business of Fashion", site("businessoffashion.com", "runway+OR+fashion+week+OR+show", 5), "Fashion & Swim"),
    ("SI Swimsuit",       site("swimsuit.si.com", days=5),    "Fashion & Swim"),
    ("Swim Week",         g("swim+week+OR+miami+swim+week+OR+paraiso+OR+si+swimsuit+when:6d"), "Fashion & Swim"),
    ("Runway",            g("fashion+week+runway+OR+victoria%27s+secret+fashion+show+OR+runway+show+when:4d"), "Fashion & Swim"),
    ("Festival Fashion",  g("coachella+fashion+OR+festival+outfit+OR+rave+outfit+when:5d"), "Fashion & Swim"),
    # ── Retro & Culture ──
    ("Far Out",           site("faroutmagazine.co.uk", "festival+OR+tour+OR+mtv+OR+live+OR+rave", 4), "Retro & Culture"),
    ("Dazed",             site("dazeddigital.com", "club+OR+rave+OR+party+OR+fashion+OR+music", 5), "Retro & Culture"),
    ("i-D",               site("i-d.co", "club+OR+rave+OR+party+OR+fashion+OR+music", 6), "Retro & Culture"),
    ("PAPER",             site("papermag.com", "party+OR+club+OR+nightlife+OR+fashion+OR+music", 5), "Retro & Culture"),
    ("VICE Music",        site("vice.com", "rave+OR+club+OR+party+OR+festival+OR+music", 5), "Retro & Culture"),
    ("MTV",               site("mtv.com", days=6),            "Retro & Culture"),
    ("Retro MTV",         g("mtv+throwback+OR+music+video+anniversary+OR+90s+nostalgia+OR+y2k+when:5d"), "Retro & Culture"),
    ("Counterculture",    g("%22underground+rave%22+OR+%22free+party%22+OR+%22sound+system%22+OR+%22rave+culture%22+when:7d"), "Retro & Culture"),
    ("Art Basel / Miami Art Week", g("art+basel+miami+party+OR+miami+art+week+OR+art+basel+dj+when:6d"), "Retro & Culture"),

    # ══ 3.2 (ORDER-701 C5): a NUZU-wide net - more outlets per tab, and short topic searches so the
    # same story is seen from many outlets and counted (the Top 10 ranks by that count). ══
    # ── EDM & Dance ──
    ("EDM Joy",           site("edmjoy.com", days=5),          "EDM & Dance"),
    ("DJ sets",           g("%22dj+set%22+OR+b2b+OR+%22back+to+back%22+dj+when:2d"), "EDM & Dance"),
    ("Trance",            g("trance+OR+%22armin+van+buuren%22+OR+%22above+%26+beyond%22+OR+%22ferry+corsten%22+when:4d"), "EDM & Dance"),
    ("Bass music",        g("dubstep+OR+%22bass+music%22+OR+riddim+OR+excision+OR+subtronics+when:4d"), "EDM & Dance"),
    ("Drum & bass",       g("%22drum+and+bass%22+OR+%22drum+%26+bass%22+OR+%22jungle+rave%22+when:5d"), "EDM & Dance"),
    ("Big-room DJs",      g("%22david+guetta%22+OR+%22martin+garrix%22+OR+%22calvin+harris%22+OR+tiesto+OR+%22dj+snake%22+when:3d"), "EDM & Dance"),
    ("Dance releases",    g("%22new+single%22+dj+OR+%22new+remix%22+OR+%22dance+track%22+when:2d"), "EDM & Dance"),
    ("Insomniac events",  g("insomniac+events+OR+%22beyond+wonderland%22+OR+%22nocturnal+wonderland%22+OR+%22escape+halloween%22+when:6d"), "Festivals"),
    # ── Techno & House ──
    ("The Quietus",       site("thequietus.com", "techno+OR+club+OR+rave+OR+electronic", 7), "Techno & House"),
    ("Techno",            g("techno+when:2d"),                 "Techno & House"),
    ("House music",       g("%22house+music%22+OR+%22tech+house%22+OR+%22deep+house%22+when:2d"), "Techno & House"),
    ("Boiler Room",       g("%22boiler+room%22+when:5d"),      "Techno & House"),
    ("Afterlife / Anyma", g("anyma+OR+%22tale+of+us%22+OR+argy+OR+%22afterlife+festival%22+OR+%22afterlife+ibiza%22+when:4d"), "Techno & House"),
    ("Keinemusik",        g("keinemusik+OR+%22adam+port%22+OR+%26me+OR+rampa+OR+%22black+coffee%22+when:5d"), "Techno & House"),
    ("House headliners",  g("%22fred+again%22+OR+%22john+summit%22+OR+%22dom+dolla%22+OR+%22chris+lake%22+OR+%22fisher%22+dj+when:4d"), "Techno & House"),
    ("Techno headliners", g("%22carl+cox%22+OR+%22charlotte+de+witte%22+OR+%22amelie+lens%22+OR+%22adam+beyer%22+when:5d"), "Techno & House"),
    ("Cercle",            g("cercle+set+OR+%22cercle+festival%22+OR+%22cercle+odyssey%22+when:7d"), "Techno & House"),
    # ── Festivals ──
    ("Tomorrowland",      g("tomorrowland+when:3d"),           "Festivals"),
    ("Lollapalooza",      g("lollapalooza+when:5d"),           "Festivals"),
    ("Rolling Loud",      g("%22rolling+loud%22+when:4d"),     "Festivals"),
    ("Glastonbury",       g("glastonbury+festival+when:4d"),   "Festivals"),
    ("EDC",               g("%22edc+las+vegas%22+OR+%22edc+orlando%22+OR+%22edc+mexico%22+OR+%22electric+daisy+carnival%22+when:4d"), "Festivals"),
    ("Ultra",             g("%22ultra+music+festival%22+OR+%22ultra+miami%22+OR+%22ultra+europe%22+when:4d"), "Festivals"),
    ("Festival headliners", g("%22festival+headliners%22+OR+%22to+headline%22+festival+when:3d"), "Festivals"),
    ("Festival news",     g("%22music+festival%22+when:1d"),   "Festivals"),
    ("Festival changes",  g("%22music+festival%22+cancelled+OR+canceled+OR+postponed+OR+%22new+venue%22+when:5d"), "Festivals"),
    ("Winter festivals",  g("%22nye+festival%22+OR+%22new+year%27s+festival%22+OR+%22winter+festival%22+music+when:7d"), "Festivals"),
    # ── Tickets & Lineups ──
    ("Tickets on sale",   g("%22tickets+on+sale%22+tour+OR+concert+OR+festival+when:2d"), "Tickets & Lineups"),
    ("Presales",          g("presale+tour+OR+%22presale+code%22+OR+%22pre-sale%22+concert+when:2d"), "Tickets & Lineups"),
    ("Sold out",          g("%22sold+out%22+concert+OR+tour+OR+festival+when:3d"), "Tickets & Lineups"),
    ("Lineups revealed",  g("%22lineup+revealed%22+OR+%22unveils+lineup%22+OR+%22announces+lineup%22+when:3d"), "Tickets & Lineups"),
    ("New dates",         g("%22adds+dates%22+OR+%22new+dates%22+tour+OR+%22second+show%22+when:3d"), "Tickets & Lineups"),
    ("TicketNews",        site("ticketnews.com", days=4),      "Tickets & Lineups"),
    # ── Nightlife & Clubs ──
    ("Club openings",     g("%22new+nightclub%22+OR+%22club+opening%22+OR+%22opens+nightclub%22+when:5d"), "Nightlife & Clubs"),
    ("Rooftops",          g("%22rooftop+bar%22+OR+%22rooftop+party%22+when:4d"), "Nightlife & Clubs"),
    ("Pool & beach clubs",g("%22pool+party%22+OR+%22beach+club%22+when:4d"), "Nightlife & Clubs"),
    ("NYE parties",       g("%22new+year%27s+eve%22+party+OR+%22nye+party%22+OR+%22new+year%27s+eve%22+dj+when:5d"), "Nightlife & Clubs"),
    ("After hours",       g("%22after+hours%22+club+OR+afterparty+OR+%22after-party%22+when:4d"), "Nightlife & Clubs"),
    ("Eater nightlife",   site("eater.com", "nightlife+OR+%22dance+club%22+OR+rooftop", 6), "Nightlife & Clubs"),
    ("Discotech",         site("discotech.me", days=7),        "Nightlife & Clubs"),
    ("Chicago Nightlife", g("%22chicago+nightlife%22+OR+%22chicago+club%22+when:6d"), "Nightlife & Clubs"),
    ("Texas Nightlife",   g("%22austin+nightlife%22+OR+%22houston+nightlife%22+OR+%22dallas+nightlife%22+when:7d"), "Nightlife & Clubs"),
    ("Atlanta Nightlife", g("%22atlanta+nightlife%22+OR+%22atlanta+club%22+when:6d"), "Nightlife & Clubs"),
    ("SF Nightlife",      g("%22san+francisco+nightlife%22+OR+%22sf+club%22+OR+%22oakland+club%22+when:7d"), "Nightlife & Clubs"),
    ("Canada Nightlife",  g("%22toronto+nightlife%22+OR+%22montreal+nightlife%22+OR+%22vancouver+nightlife%22+when:7d"), "Nightlife & Clubs"),
    # ── Las Vegas ──
    ("Sphere",            g("sphere+%22las+vegas%22+when:3d"), "Las Vegas"),
    ("Vegas residencies", g("%22las+vegas+residency%22+OR+%22vegas+residency%22+when:3d"), "Las Vegas"),
    ("Vegas clubs",       g("%22vegas+nightclub%22+OR+zouk+OR+omnia+OR+%22xs+nightclub%22+OR+hakkasan+when:5d"), "Las Vegas"),
    ("Vegas concerts",    g("%22las+vegas%22+concert+OR+%22las+vegas%22+show+when:2d"), "Las Vegas"),
    ("Vegas NYE",         g("%22las+vegas%22+%22new+year%27s+eve%22+OR+%22vegas+nye%22+when:7d"), "Las Vegas"),
    ("Las Vegas Magazine",site("lasvegasmagazine.com", days=7), "Las Vegas"),
    ("Eater Vegas",       site("vegas.eater.com", days=7),     "Las Vegas"),
    ("Casino.org Vegas",  site("casino.org", "%22las+vegas%22+nightclub+OR+residency+OR+concert+OR+sphere", 5), "Las Vegas"),
    # ── Ibiza & Global ──
    ("Ibiza news",        g("ibiza+when:3d"),                  "Ibiza & Global"),
    ("Bali / Thailand",   g("%22bali+nightlife%22+OR+%22bali+club%22+OR+%22koh+phangan%22+OR+%22full+moon+party%22+when:7d"), "Ibiza & Global"),
    ("Tulum",             g("tulum+festival+OR+tulum+party+OR+tulum+dj+when:6d"), "Ibiza & Global"),
    ("Carnivals",         g("%22notting+hill+carnival%22+OR+%22trinidad+carnival%22+OR+caribana+OR+%22rio+carnival%22+when:7d"), "Ibiza & Global"),
    ("ADE / Amsterdam",   g("%22amsterdam+dance+event%22+OR+%22amsterdam+club%22+when:7d"), "Ibiza & Global"),
    ("Asia clubs",        g("%22seoul+club%22+OR+%22tokyo+club%22+OR+%22shanghai+club%22+OR+%22bangkok+club%22+when:7d"), "Ibiza & Global"),
    ("Australia / NZ",    g("%22sydney+festival%22+OR+%22melbourne+festival%22+OR+%22rhythm+and+vines%22+OR+%22field+day%22+sydney+when:7d"), "Ibiza & Global"),
    ("Africa / Detty December", g("%22afro+nation%22+OR+%22detty+december%22+OR+%22lagos+concert%22+OR+%22cape+town%22+festival+when:7d"), "Ibiza & Global"),
    ("Dubai / Middle East", g("%22dubai+nightlife%22+OR+%22dubai+club%22+OR+%22soundstorm%22+OR+%22mdlbeast%22+when:7d"), "Ibiza & Global"),
    ("Mediterranean",     g("mykonos+OR+%22ayia+napa%22+OR+hvar+OR+%22zrce+beach%22+party+when:7d"), "Ibiza & Global"),
    # ── Hip-Hop ──
    ("Rap tours",         g("rapper+tour+OR+%22rap+tour%22+when:3d"), "Hip-Hop"),
    ("Hip-hop live",      g("%22hip+hop%22+concert+OR+%22hip-hop%22+festival+when:3d"), "Hip-Hop"),
    ("Rap charts",        g("rapper+%22billboard+200%22+OR+rap+album+debuts+when:3d"), "Hip-Hop"),
    ("Rap headliners",    g("drake+OR+%22kendrick+lamar%22+OR+%22travis+scott%22+OR+%22tyler,+the+creator%22+tour+OR+concert+when:4d"), "Hip-Hop"),
    ("Summer Jam / Wireless", g("%22summer+jam%22+OR+%22wireless+festival%22+OR+%22day+n+vegas%22+when:7d"), "Hip-Hop"),
    # ── Rock ──
    ("Guitar World",      site("guitarworld.com", "tour+OR+festival+OR+live", 5), "Rock"),
    ("Lambgoat",          site("lambgoat.com", days=5),        "Rock"),
    ("American Songwriter", site("americansongwriter.com", "tour+OR+concert+OR+festival", 5), "Rock"),
    ("Rock festivals",    g("%22rock+festival%22+OR+%22metal+festival%22+OR+hellfest+OR+wacken+OR+%22download+festival%22+when:5d"), "Rock"),
    ("Farewell & reunion",g("%22farewell+tour%22+OR+%22reunion+tour%22+OR+%22reunite%22+band+when:4d"), "Rock"),
    ("Punk & emo",        g("punk+tour+OR+%22emo+nite%22+OR+%22when+we+were+young%22+OR+%22sick+new+world%22+when:6d"), "Rock"),
    ("Rock stadiums",     g("metallica+OR+%22foo+fighters%22+OR+%22green+day%22+OR+%22linkin+park%22+tour+when:4d"), "Rock"),
    # ── Pop & Tours ──
    ("World tours",       g("%22world+tour+dates%22+OR+%22announces+world+tour%22+OR+%22world+tour%22+concert+when:3d"), "Pop & Tours"),
    ("Stadium tours",     g("%22stadium+tour%22+OR+%22arena+tour%22+when:3d"), "Pop & Tours"),
    ("Album + tour",      g("%22new+album%22+tour+when:2d"),   "Pop & Tours"),
    ("Pop superstars",    g("%22taylor+swift%22+OR+beyonce+OR+%22bad+bunny%22+OR+%22the+weeknd%22+tour+OR+concert+when:3d"), "Pop & Tours"),
    ("Pop rising",        g("%22sabrina+carpenter%22+OR+%22chappell+roan%22+OR+%22charli+xcx%22+OR+%22dua+lipa%22+OR+%22olivia+rodrigo%22+when:3d"), "Pop & Tours"),
    ("Awards",            g("grammys+OR+%22grammy+nominations%22+OR+%22american+music+awards%22+OR+vmas+when:4d"), "Pop & Tours"),
    ("Concert reviews",   g("%22concert+review%22+OR+%22live+review%22+tour+when:3d"), "Pop & Tours"),
    ("USA TODAY Music",   site("usatoday.com", "tour+OR+concert+OR+festival", 3), "Pop & Tours"),
    ("People Music",      site("people.com", "tour+OR+concert+OR+festival", 3), "Pop & Tours"),
    ("E! News Music",     site("eonline.com", "tour+OR+concert+OR+festival", 4), "Pop & Tours"),
    ("ET Music",          site("etonline.com", "tour+OR+concert+OR+festival", 4), "Pop & Tours"),
    ("Hollywood Reporter Music", site("hollywoodreporter.com", "tour+OR+concert+OR+festival", 4), "Pop & Tours"),
    ("Vulture Music",     site("vulture.com", "tour+OR+concert+OR+festival", 5), "Pop & Tours"),
    ("Live Nation news",  g("%22live+nation%22+tour+OR+%22live+nation%22+festival+when:5d"), "Pop & Tours"),
    # ── Fashion & Swim ──
    ("Fashion shows",     g("%22fashion+show%22+when:2d"),     "Fashion & Swim"),
    ("Runway shows",      g("%22runway+show%22+OR+%22walks+the+runway%22+OR+%22catwalk%22+when:3d"), "Fashion & Swim"),
    ("Swim runways",      g("swimwear+show+OR+bikini+runway+OR+%22swim+show%22+when:6d"), "Fashion & Swim"),
    ("Victoria's Secret", g("%22victoria%27s+secret%22+show+OR+%22victoria%27s+secret+fashion+show%22+when:5d"), "Fashion & Swim"),
    ("Fashion weeks",     g("%22paris+fashion+week%22+OR+%22milan+fashion+week%22+OR+%22new+york+fashion+week%22+OR+%22london+fashion+week%22+when:5d"), "Fashion & Swim"),
    ("Fashion awards",    g("%22met+gala%22+OR+%22fashion+awards%22+OR+%22cfda%22+when:5d"), "Fashion & Swim"),
    ("Supermodels",       g("supermodel+OR+%22model+walks%22+OR+%22runway+debut%22+when:4d"), "Fashion & Swim"),
    ("British Vogue",     site("vogue.co.uk", "runway+OR+fashion+week+OR+party+OR+festival", 4), "Fashion & Swim"),
    ("W Magazine",        site("wmagazine.com", "fashion+OR+party+OR+runway", 6), "Fashion & Swim"),
    ("Refinery29",        site("refinery29.com", "fashion+week+OR+runway+OR+festival", 6), "Fashion & Swim"),
    ("Who What Wear",     site("whowhatwear.com", "runway+OR+fashion+week+OR+festival", 6), "Fashion & Swim"),
    ("NYLON",             site("nylon.com", "fashion+OR+party+OR+music+OR+festival", 6), "Fashion & Swim"),
    ("FashionUnited",     site("fashionunited.com", "runway+OR+fashion+week+OR+show", 5), "Fashion & Swim"),
    # ── Retro & Culture ──
    ("Music anniversaries", g("%22years+ago+today%22+album+OR+%22music+video%22+anniversary+when:4d"), "Retro & Culture"),
    ("MTV news",          g("mtv+when:3d"),                    "Retro & Culture"),
    ("Music documentaries", g("music+documentary+OR+music+biopic+OR+%22concert+film%22+when:4d"), "Retro & Culture"),
    ("Rock Hall",         g("%22rock+hall+of+fame%22+OR+%22rock+%26+roll+hall+of+fame%22+when:6d"), "Retro & Culture"),
    ("Art Basel",         g("%22art+basel%22+when:4d"),        "Retro & Culture"),
    ("Pop culture",       site("avclub.com", "music+OR+tour+OR+concert", 5), "Retro & Culture"),
]
CULTURE_SOURCES = [(n, u) for n, u, _h in NEWS_SOURCES]   # (kept for the 2.x test tools)
SOURCE_HOME = {n: h for n, _u, h in NEWS_SOURCES}

# ───────────────────────── FETCH + PARSE ───────────────────────────
def _fetch_rss(name, url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PartyPortalBot/3.0)",
               "Accept": "application/rss+xml, application/xml, text/xml"}
    try:
        raw = b""
        for _attempt in range(3):     # 3.2: Google News answers a burst with 429/503 - wait, then retry
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                    raw = resp.read()
                break
            except urllib.error.HTTPError as _he:
                if _he.code in (429, 503) and _attempt < 2:
                    time.sleep((2, 6)[_attempt])
                    continue
                raise
        root = ET.fromstring(raw)
        out = []
        for item in root.iter("item"):
            t_el = item.find("title")
            l_el = item.find("link")
            p_el = item.find("pubDate")
            s_el = item.find("source")
            if t_el is None or not t_el.text:
                continue
            title = htmllib.unescape(t_el.text.strip())
            link  = (l_el.text or "").strip() if l_el is not None else ""
            src   = s_el.text.strip() if (s_el is not None and s_el.text) else name
            if src.lower().startswith(("http://", "https://")):      # some outlets publish a bare URL as their name
                src = re.sub(r"^https?://(www\.)?", "", src).strip("/").split("/")[0]
            domain = ""
            if s_el is not None:
                m = re.search(r"https?://([^/]+)", s_el.get("url") or "")
                if m:
                    domain = m.group(1).lower().replace("www.", "")
            ts = 0
            if p_el is not None and p_el.text:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
                    try:
                        dt = datetime.strptime(p_el.text.strip(), fmt)
                        ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt.tzinfo is None else int(dt.timestamp())
                        break
                    except ValueError:
                        pass
            if not ts:
                ts = int(time.time()) - 3600
            out.append((ts, title, link, src, domain, name))
        return out
    except Exception as e:
        print(f"  [WARN] {name}: {e}")
        FEED_ERRORS[name] = str(e)[:120]
        return []

FEED_STATS = {}
FEED_ERRORS = {}      # 3.2: feed name -> why it failed (health.json)

def fetch_all():
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_rss, n, u): n for n, u in CULTURE_SOURCES}
        for f in as_completed(futures):
            r = f.result()
            FEED_STATS[futures[f]] = len(r)
            results.extend(r)
    return results

# ──────────────────── CLEANING / JUNK DETECTION ────────────────────
def strip_source(title):
    """Remove a trailing ' - Source Name' (<=5 words) appended by Google News."""
    title = re.sub(r"\s*(?:·\s*News\s*)?⟋\s*RA\s*$", "", title)
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
    "week in review |", "watch live:", "live updates:", "photos:", "photo gallery", "in photos",
    "see all the", "every look from", "red carpet photos",
)

# Pages Google News indexes that are not articles: RA event / artist pages, 1001Tracklists
# tracklists, ticket-listing pages, events-calendar entries, tag pages, merch, gear reviews.
_NOT_ARTICLE = re.compile(
    r"(⟋ RA$(?<!· News ⟋ RA)|· (past events|tour dates|artist|events) ⟋|\b20\d\d-\d\d-\d\d$|^events calendar -|"
    r"\| social events \||\btag \| hypebeast|\| hypebeast - fashion|\btickets, live at .{3,80} on [a-z]{3} \d{1,2}, 20\d\d|"
    r"\[appar|merchmoment|zipped wallet|wrist strap|\bbracelet\b|\+ poster|\+ t-shirt|matching beanie|better beanie|"
    r"\bholiday gifts?\b|\$\d+ .{0,30}\b(stand|headphones?|speakers?|lens(es)?|controller|turntable|mixer|monitors?)\b|"
    r"\b(lenses|glasses|headphones|earbuds|speaker|turntable|controller|mixer|monitor|plugin|synth) review\b|review: premium|"
    # 3.2: record-store product listings ("... 2LP (White/Pink Vinyl)"), not news about a reissue
    r"\([^)]{0,40}\bvinyl\)|\b[1-4]\s?lp\s*\()",
    re.I)
_OFF_FEST = re.compile(r"\b(film|book|pecan|food|wine|beer|chili|harvest|pumpkin|apple|craft|quilt|literary|poetry|comedy|"
                       r"documentary|kids'?|children'?s|christmas|lights|balloon|kite|garlic|strawberry|oyster|seafood|"
                       r"bbq|barbecue|taco|renaissance|science|theatre|theater|dance theatre|storytelling) (festival|fest)\b|"
                       r"\bfilm fest\b|\bfilm festival\b", re.I)


def is_junk(title):
    tl = title.lower()
    if _NOT_ARTICLE.search(title.strip()) or _OFF_FEST.search(title):
        return True
    for m in _TRACKING_RE.findall(title):
        if any(c.isdigit() for c in m) and any(c.isalpha() for c in m) and m != m.lower() and m != m.upper():
            return True
    for p in _JUNK_PHRASES:
        if p in tl:
            return True
    if len(title.split()) > 34:      # 2.x used 28, which also dropped real long headlines
        return True
    return False

def categorize(title, home=None):
    t = strip_source(title)
    for tab in TAB_ORDER:
        p = TAB_PATS.get(tab)
        if p and p.search(t):
            return tab
    return home or "Nightlife & Clubs"

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
             "2026 2025 2024 2027 ft feat vs after first time bring back into out over more most").split())

def _pp_stem(w):
    """3.2: NUZU 2.3's light stem, so "tours"/"touring", "announces"/"announced", "parties"/"party" match."""
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ied"):
        w = w[:-3] + "y"
    elif len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es") and w[-3] in "sxz":
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def _sigwords(title):
    t = re.sub(r"[^a-z0-9 ]", " ", strip_source(title).lower().replace("’", "'").replace("'s ", " "))
    return set(_pp_stem(w) for w in t.split() if len(w) > 3 and w not in _STOP)

_DOMAIN_MAP = {
    "mixmag": "mixmag.net", "dj mag": "djmag.com", "djmag": "djmag.com",
    "resident advisor": "ra.co", "ra": "ra.co", "edm.com": "edm.com",
    "dancing astronaut": "dancingastronaut.com", "your edm": "youredm.com", "edmtunes": "edmtunes.com",
    "we rave you": "weraveyou.com", "edm identity": "edmidentity.com", "billboard": "billboard.com",
    "rolling stone": "rollingstone.com", "pitchfork": "pitchfork.com", "stereogum": "stereogum.com",
    "nme": "nme.com", "consequence": "consequence.net", "variety": "variety.com",
    "the guardian": "theguardian.com", "spin": "spin.com", "loudwire": "loudwire.com",
    "ultimate classic rock": "ultimateclassicrock.com", "kerrang": "kerrang.com", "kerrang!": "kerrang.com",
    "magnetic magazine": "magneticmag.com", "6am": "6amgroup.com", "the nocturnal times": "thenocturnaltimes.com",
    "edm sauce": "edmsauce.com", "data transmission": "datatransmission.co", "decoded magazine": "decodedmagazine.com",
    "when we dip": "whenwedip.com", "mixmag asia": "mixmag.asia", "attack magazine": "attackmagazine.com",
    "ibiza spotlight": "ibiza-spotlight.com", "edm maniac": "edmmaniac.com", "brooklyn vegan": "brooklynvegan.com",
    "brooklynvegan": "brooklynvegan.com", "hiphopdx": "hiphopdx.com", "music festival wizard": "musicfestivalwizard.com",
    "time out": "timeout.com", "revolver": "revolvermag.com", "metal injection": "metalinjection.net",
    "xxl": "xxlmag.com", "xxl mag": "xxlmag.com", "rap-up": "rap-up.com", "ravejungle": "ravejungle.com",
    "rave jungle": "ravejungle.com", "xlr8r": "xlr8r.com", "beatportal": "beatportal.com", "vogue": "vogue.com",
    "wwd": "wwd.com", "harper's bazaar": "harpersbazaar.com", "elle": "elle.com", "fashionista": "fashionista.com",
    "hypebeast": "hypebeast.com", "highsnobiety": "highsnobiety.com", "far out magazine": "faroutmagazine.co.uk",
    "dazed": "dazeddigital.com", "the face": "theface.com", "paper": "papermag.com", "paper magazine": "papermag.com",
    "las vegas review-journal": "reviewjournal.com", "las vegas weekly": "lasvegasweekly.com", "vital vegas": "vitalvegas.com",
    "las vegas sun": "lasvegassun.com", "pollstar": "pollstar.com", "iq magazine": "iqmagazine.com",
    "jambase": "jambase.com", "complex": "complex.com", "hotnewhiphop": "hotnewhiphop.com", "vibe": "vibe.com",
    "revolt": "revolt.tv", "okayplayer": "okayplayer.com", "uproxx": "uproxx.com", "louder": "loudersound.com",
    "blabbermouth": "blabbermouth.net", "blabbermouth.net": "blabbermouth.net", "alternative press": "altpress.com",
    "electronic groove": "electronicgroove.com", "run the trap": "runthetrap.com", "dj times": "djtimes.com",
    "clash": "clashmusic.com", "fact": "factmag.com", "electronic beats": "electronicbeats.net",
    "entertainment weekly": "ew.com", "sports illustrated swimsuit": "swimsuit.si.com", "mtv": "mtv.com",
    "vital vegas": "vitalvegas.com", "the fader": "thefader.com", "exclaim!": "exclaim.ca", "paste": "pastemagazine.com",
    "paste magazine": "pastemagazine.com", "allhiphop": "allhiphop.com", "remezcla": "remezcla.com",
    "music week": "musicweek.com", "the line of best fit": "thelineofbestfit.com", "diy": "diymag.com",
    "dance music nw": "dancemusicnw.com", "rolling out": "rollingout.com", "hiphop-n-more": "hiphop-n-more.com",
}
def _guess_domain(src):
    if not src:
        return ""
    return _DOMAIN_MAP.get(src.strip().lower(), "")

def build_item(ts, title, link, src, domain="", home=None):
    """Apply all cleaning/filters. Return dict or None if rejected."""
    if len(title) < MIN_TITLE_LEN or len(title) > MAX_TITLE_LEN:
        return None
    if is_junk(title):
        return None
    why = why_promo(title, src)
    if why:
        _PP_PROMO_LOG[why] = _PP_PROMO_LOG.get(why, 0) + 1
        return None
    if _PP_SKIP_SRC.search(src or "") or _PP_SKIP_SRC.search(domain or ""):
        _PP_PROMO_LOG["off-topic outlet"] = _PP_PROMO_LOG.get("off-topic outlet", 0) + 1
        return None
    clean = strip_source(title)
    if BLOCK_PAT and BLOCK_PAT.search(clean):
        return None
    if not (KEYWORD_PAT and KEYWORD_PAT.search(clean)):
        if not is_niche(src):
            return None
    now = int(time.time())
    age = now - ts
    return {
        "title": clean,
        "link":  link or "#",
        "src":   src,
        "domain": domain or _guess_domain(src),
        "time":  time_label(age),
        "cat":   categorize(clean, home),
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
    """Pacific-time calendar day (UTC-7), matching the site's local-day news columns."""
    return time.strftime("%Y-%m-%d", time.gmtime(int(ts) - 7 * 3600))

def filter_and_dedup(raw):
    """Filter, then collapse exact AND near-duplicate headlines (Jaccard of significant
    words >= 0.55), keeping the higher-trust source. n = distinct outlets reporting it.
    A per-source-per-day cap keeps any one outlet from flooding the feed."""
    now = int(time.time())
    max_age = DAILY_HOURS * 3600
    raw.sort(key=lambda x: x[0], reverse=True)
    out, sigs, srcsets = [], [], []
    names = []          # 3.2: per story, outlet id -> the outlet's name (for "also")
    exact_idx = {}
    src_count = {}
    for tup in raw:
        ts, title, link, src = tup[0], tup[1], tup[2], tup[3]
        domain = tup[4] if len(tup) > 4 else ""
        home = SOURCE_HOME.get(tup[5]) if len(tup) > 5 else None
        if (now - ts) > max_age:
            continue
        it = build_item(ts, title, link, src, domain, home)
        if not it:
            continue
        srcid = _base_domain((it.get("domain") or src or "").lower())
        h = hashlib.md5(_key(title).encode()).hexdigest()
        if h in exact_idx:
            j = exact_idx[h]
            if srcid:
                srcsets[j].add(srcid)
                names[j].setdefault(srcid, it["src"])
            out[j]["n"] = max(1, len(srcsets[j]))
            continue
        sg = _sigwords(title)
        dup = -1
        if sg:
            for i, prev in enumerate(sigs):
                if not prev:
                    continue
                if abs(out[i].get("ts", 0) - ts) > 86400:     # 3.2: one story = within 24 hours
                    continue
                inter = len(sg & prev)
                union = len(sg | prev)
                if union and ((inter / union) >= 0.55 or (inter >= 4 and inter / min(len(sg), len(prev)) >= 0.6)):
                    dup = i
                    break
        if dup >= 0:
            if srcid:
                srcsets[dup].add(srcid)
                names[dup].setdefault(srcid, it["src"])
            if it["tier"] < out[dup]["tier"]:
                it["n"] = max(1, len(srcsets[dup]))
                out[dup] = it
                sigs[dup] = sg
                exact_idx[h] = dup
            else:
                out[dup]["n"] = max(1, len(srcsets[dup]))
            continue
        ck = (srcid, _day_key(ts))
        if src_count.get(ck, 0) >= PER_SOURCE_MAX:
            continue
        src_count[ck] = src_count.get(ck, 0) + 1
        exact_idx[h] = len(out)
        out.append(it)
        sigs.append(sg)
        srcsets.append(set([srcid]) if srcid else set())
        names.append({srcid: it["src"]} if srcid else {})
        if len(out) >= MAX_ITEMS * 12:      # 3.2: was 3x - with a NUZU-wide net that cut the count short
            break
    # 3.2: "also" = the other outlets reporting the story (up to 5); hot (the fire) only when
    # two or more outlets report it and it is under 24 hours old (it was every story under 36 h).
    for j, it in enumerate(out):
        lead = (it.get("src") or "").strip().lower()
        it["also"] = [nm for nm in names[j].values() if nm and nm.strip().lower() != lead][:5]
        it["hot"] = it.get("n", 1) >= 2 and (now - it.get("ts", 0)) < 24 * 3600
    byday = {}
    for it in out:
        byday.setdefault(_day_key(it.get("ts", 0)), []).append(it)
    final = []
    for d in sorted(byday.keys(), reverse=True)[:2]:
        day_items = sorted(byday[d], key=lambda x: (x.get("n", 1), x.get("ts", 0)), reverse=True)
        # keep every tab represented before the per-day cap trims the list
        picked, seen_tab = [], {}
        for it in day_items:
            if seen_tab.get(it["cat"], 0) < 3:
                picked.append(it); seen_tab[it["cat"]] = seen_tab.get(it["cat"], 0) + 1
        for it in day_items:
            if it not in picked:
                picked.append(it)
        final.extend(picked[:PER_DAY_MAX])
    final.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return final[:MAX_ITEMS]

# ═════════════════════════ ON THE HORIZON (events.json) ═════════════════════════
# 1) FESTIVALS — the big ones, with dates their organisers have announced (checked
#    7 Nov 2026). An edition drops off automatically after it ends; add next year's
#    when it is announced. Never guess a date: unannounced editions are left out
#    (Tomorrowland Belgium, Lollapalooza and Sziget 2027 were not announced yet).
FESTIVALS = [
    # name, emoji, venue/where, city, region, start (local ISO), end (local ISO), label, url, wall search
    ("EDC Orlando", "\U0001F3A1", "Tinker Field", "Orlando, FL", "world", "2026-11-06T16:00:00-05:00", "2026-11-08T23:59:00-05:00", "Nov 6–8", "https://orlando.electricdaisycarnival.com", "edc"),
    ("F1 Las Vegas Grand Prix", "\U0001F3CE️", "Las Vegas Strip Circuit", "Las Vegas", "vegas", "2026-11-19T20:00:00-08:00", "2026-11-21T23:59:00-08:00", "Nov 19–21", "https://www.f1lasvegasgp.com", ""),
    ("Dreamstate SoCal", "\U0001F30C", "Queen Mary Waterfront", "Long Beach, CA", "la", "2026-11-20T15:00:00-08:00", "2026-11-21T23:59:00-08:00", "Nov 20–21", "https://socal.dreamstateusa.com", "trance"),
    ("Art Basel Miami Beach", "\U0001F3A8", "Miami Beach Convention Center · Miami Art Week parties", "Miami Beach", "miami", "2026-12-04T11:00:00-05:00", "2026-12-06T19:00:00-05:00", "Dec 4–6", "https://www.artbasel.com/miami-beach", ""),
    ("Sunburn Festival", "☀️", "Mahalaxmi Racecourse", "Mumbai, India", "world", "2026-12-18T15:00:00+05:30", "2026-12-19T23:59:00+05:30", "Dec 18–19", "https://www.sunburn.in", ""),
    ("Zamna Tulum", "\U0001F334", "Zamna · 10th anniversary season", "Tulum, Mexico", "world", "2026-12-31T20:00:00-05:00", "2027-01-10T23:59:00-05:00", "Dec 31 – Jan 10", "https://zamnafestival.com", "tulum"),
    ("Day Zero Tulum", "\U0001F311", "Jungle near Tulum · sunset to sunrise", "Tulum, Mexico", "world", "2027-01-09T17:00:00-05:00", "2027-01-10T08:00:00-05:00", "Jan 9", "https://dayzerofestival.com/tulum/", "tulum"),
    # ── 3.2 (ORDER-701 C9): the winter calendar - New Year's Eve worldwide, the Australia / New Zealand
    #    summer, the Thailand season, Tulum. Every date checked on the organiser's, city's or tourism
    #    board's own page on 21 Nov 2026 (the URL is the page). Where no time was published: 18:00 local
    #    start, 23:59 (or 02:00 after New Year's Eve) end. An optional 11th value True = runs through NYE.
    #    Left out, not announced yet: Auckland Sky Tower NYE 2026 (its 2026 page is not up), Falls Festival
    #    (on hiatus), Origin Fields, Juicy Fest, FOMO, Afterlife Tulum, Full Moon Party dates (no official
    #    calendar), S2O and Ultra Australia (April).
    ("Wonderfruit", "\U0001F349", "The Fields at Siam Country Club", "Pattaya, Thailand", "world", "2026-12-03T18:00:00+07:00", "2026-12-07T23:59:00+07:00", "Dec 3–7", "https://wonderfruit.co/", ""),
    ("Tomorrowland Thailand", "\U0001F3AA", "Wisdom Valley", "Pattaya, Thailand", "world", "2026-12-11T18:00:00+07:00", "2026-12-13T23:59:00+07:00", "Dec 11–13", "https://thailand.tomorrowland.com/", "tomorrowland"),
    ("EDC Thailand", "\U0001F3A1", "Rhythm Park", "Phuket, Thailand", "world", "2026-12-18T15:00:00+07:00", "2026-12-21T00:00:00+07:00", "Dec 18–20", "https://thailand.edc.com/", "edc"),
    ("Beyond The Valley", "\U0001F3A7", "Barunah Plains, Hesse VIC", "Hesse, Australia", "world", "2026-12-28T18:00:00+11:00", "2027-01-01T23:59:00+11:00", "Dec 28 – Jan 1", "https://www.beyondthevalley.com.au/", "", True),
    ("Lost Paradise", "\U0001F334", "Glenworth Valley", "Central Coast, Australia", "world", "2026-12-28T18:00:00+11:00", "2027-01-01T23:59:00+11:00", "Dec 28 – Jan 1", "https://lostparadise.com.au/", "", True),
    ("Rhythm and Vines", "\U0001F347", "Waiohika Estate", "Gisborne, New Zealand", "world", "2026-12-29T18:00:00+13:00", "2027-01-01T02:00:00+13:00", "Dec 29–31", "https://www.rhythmandvines.co.nz/", "", True),
    ("Northern Bass", "\U0001F50A", "Settlement Road, Kaiwaka", "Kaiwaka, New Zealand", "world", "2026-12-30T18:00:00+13:00", "2027-01-01T23:59:00+13:00", "Dec 30 – Jan 1", "https://northernbass.co.nz/", "", True),
    ("Sydney New Year's Eve Fireworks", "\U0001F386", "Sydney Harbour", "Sydney, Australia", "world", "2026-12-31T19:30:00+11:00", "2027-01-01T00:12:00+11:00", "Dec 31", "https://www.sydneynewyearseve.com/", ""),
    ("Tokyo New Year's Eve Countdown", "\U0001F386", "Odaiba Marine Park", "Tokyo, Japan", "world", "2026-12-31T18:00:00+09:00", "2027-01-01T00:10:00+09:00", "Dec 31", "https://tokyo-nighttime-project.jp/en/tny/", ""),
    ("Hong Kong New Year Countdown Fireworks", "\U0001F386", "Victoria Harbour", "Hong Kong", "world", "2026-12-31T18:00:00+08:00", "2027-01-01T02:00:00+08:00", "Dec 31", "https://www.discoverhongkong.com/eng/events/hong-kong-winterfest.html", ""),
    ("Amazing Thailand Countdown 2027", "\U0001F386", "River Park, ICONSIAM", "Bangkok, Thailand", "world", "2026-12-31T18:00:00+07:00", "2027-01-01T02:00:00+07:00", "Dec 31", "https://www.tatnews.org/2026/11/tat-and-iconsiam-unveil-amazing-thailand-countdown-2027-in-bangkok/", ""),
    ("Burj Khalifa New Year's Eve Fireworks", "\U0001F386", "Burj Khalifa, Downtown Dubai", "Dubai, UAE", "world", "2026-12-31T19:00:00+04:00", "2027-01-01T02:00:00+04:00", "Dec 31", "https://mydubainewyear.emaar.com/", ""),
    ("Wildlands Brisbane", "\U0001F3A7", "Brisbane Showgrounds", "Brisbane, Australia", "world", "2026-12-31T18:00:00+10:00", "2027-01-01T02:00:00+10:00", "Dec 31", "https://wildlandsfestival.com.au/", ""),
    ("Silvester am Brandenburger Tor", "\U0001F386", "Brandenburger Tor", "Berlin, Germany", "world", "2026-12-31T20:00:00+01:00", "2027-01-01T01:00:00+01:00", "Dec 31", "https://www.berlin.de/en/events/3303144-2842498-silvester-am-brandenburger-tor-2026.en.html", "berlin"),
    ("New Year's Eve on the Champs-Élysées", "\U0001F386", "Champs-Élysées · Arc de Triomphe", "Paris, France", "world", "2026-12-31T19:00:00+01:00", "2027-01-01T00:20:00+01:00", "Dec 31", "https://parisjetaime.com/eng/event/31-december-champs-elysees-e081", ""),
    ("London New Year's Eve Fireworks", "\U0001F386", "River Thames by the London Eye (ticketed)", "London, UK", "world", "2026-12-31T20:00:00+00:00", "2027-01-01T00:30:00+00:00", "Dec 31", "https://www.london.gov.uk/events/london-new-years-eve-2026", ""),
    ("Réveillon Rio Copacabana", "\U0001F386", "Palco Rio, Copacabana Beach", "Rio de Janeiro", "world", "2026-12-31T18:00:00-03:00", "2027-01-01T02:00:00-03:00", "Dec 31", "https://riotur.rio/editorial/rio-reveillon-2027/", ""),
    ("Times Square Ball Drop", "\U0001F386", "Times Square", "New York", "nyc", "2026-12-31T18:00:00-05:00", "2027-01-01T02:00:00-05:00", "Dec 31", "https://www.timessquarenyc.org/nye/nye-faq", ""),
    ("The Countdown Miami NYE", "\U0001F386", "Bayfront Park", "Miami", "miami", "2026-12-31T17:00:00-05:00", "2027-01-01T02:00:00-05:00", "Dec 31", "https://thecountdownmiami.com/2027/", ""),
    ("America's Party: Las Vegas New Year", "\U0001F386", "Las Vegas Strip fireworks", "Las Vegas", "vegas", "2026-12-31T18:00:00-08:00", "2027-01-01T02:00:00-08:00", "Dec 31", "https://lasvegasevents.com/signature-events/181/americas-party", ""),
    ("NYELA Countdown to 2027", "\U0001F386", "Gloria Molina Grand Park", "Los Angeles", "la", "2026-12-31T20:00:00-08:00", "2027-01-01T01:00:00-08:00", "Dec 31", "https://grandparkla.org/nyela", ""),
    ("Field Day", "\U0001F3A7", "The Domain", "Sydney, Australia", "world", "2027-01-01T18:00:00+11:00", "2027-01-01T23:59:00+11:00", "Jan 1", "https://fieldday.com.au/", ""),
    ("Wildlands Perth", "\U0001F3A7", "Arena Joondalup", "Perth, Australia", "world", "2027-01-02T18:00:00+08:00", "2027-01-02T23:59:00+08:00", "Jan 2", "https://wildlandsfestival.com.au/", ""),
    ("ANYMA presents ÆDEN Tulum", "\U0001F3A7", "Zamna Tulum", "Tulum, Mexico", "world", "2027-01-04T22:00:00-05:00", "2027-01-04T23:59:00-05:00", "Jan 4", "https://zamnafestival.com/events/Anyma-Tulum2026", "anyma"),
    ("Laneway Festival Sydney", "\U0001F3B8", "Centennial Park", "Sydney, Australia", "world", "2027-02-12T11:30:00+11:00", "2027-02-12T22:30:00+11:00", "Feb 12", "https://lanewayfestival.com/sydney/event-info", ""),
    ("Laneway Festival Brisbane", "\U0001F3B8", "Brisbane Showgrounds", "Brisbane, Australia", "world", "2027-02-13T12:00:00+10:00", "2027-02-13T22:30:00+10:00", "Feb 13", "https://lanewayfestival.com/brisbane/event-info", ""),
    ("Laneway Festival Melbourne", "\U0001F3B8", "Flemington Park", "Melbourne, Australia", "world", "2027-02-19T12:00:00+11:00", "2027-02-19T23:00:00+11:00", "Feb 19", "https://lanewayfestival.com/melbourne/event-info", ""),
    ("Laneway Festival Auckland", "\U0001F3B8", "Western Springs", "Auckland, New Zealand", "world", "2027-02-21T12:00:00+13:00", "2027-02-21T22:00:00+13:00", "Feb 21", "https://lanewayfestival.com/auckland/event-info", ""),
    ("Pitch Music & Arts", "⛺", "Mafeking, Moyston", "Moyston, Australia", "world", "2027-03-05T09:00:00+11:00", "2027-03-09T23:59:00+11:00", "Mar 5–9", "https://pitchfestival.com.au/", ""),
    ("Rio Carnival", "\U0001F483", "Sambódromo · Special Group parades", "Rio de Janeiro", "world", "2027-02-07T21:00:00-03:00", "2027-02-10T06:00:00-03:00", "Feb 7–9", "", "carnival"),
    ("Mardi Gras", "\U0001F3AD", "French Quarter · Fat Tuesday", "New Orleans, LA", "world", "2027-02-09T08:00:00-06:00", "2027-02-09T23:59:00-06:00", "Feb 9", "https://www.mardigrasneworleans.com", "new orleans"),
    ("EDC Mexico", "\U0001F33C", "Autódromo Hermanos Rodríguez", "Mexico City", "world", "2027-02-19T16:00:00-06:00", "2027-02-21T23:59:00-06:00", "Feb 19–21", "https://mexico.electricdaisycarnival.com", "edc"),
    ("Tomorrowland Winter", "❄️", "Alpe d'Huez", "Alpe d'Huez, France", "world", "2027-03-20T12:00:00+01:00", "2027-03-27T23:59:00+01:00", "Mar 20–27", "https://www.tomorrowland.com/en/winter", "tomorrowland"),
    ("Ultra Music Festival", "\U0001F3A7", "Bayfront Park", "Miami", "miami", "2027-03-26T12:00:00-04:00", "2027-03-28T23:59:00-04:00", "Mar 26–28", "https://ultramusicfestival.com", "ultra"),
    ("Coachella", "\U0001F334", "Empire Polo Club", "Indio, CA", "world", "2027-04-09T12:00:00-07:00", "2027-04-18T23:59:00-07:00", "Apr 9–11 & 16–18", "https://www.coachella.com", "coachella"),
    ("Tomorrowland Brasil", "\U0001F1E7\U0001F1F7", "Parque Maeda", "Itu, Brazil", "world", "2027-04-30T14:00:00-03:00", "2027-05-02T23:59:00-03:00", "Apr 30 – May 2", "https://www.tomorrowland.com", "tomorrowland"),
    ("Rolling Loud Florida", "\U0001F3A4", "Camping World Stadium", "Orlando, FL", "world", "2027-05-07T12:00:00-04:00", "2027-05-09T23:59:00-04:00", "May 7–9", "https://www.rollingloud.com", "rolling loud"),
    ("EDC Las Vegas", "⚡", "Las Vegas Motor Speedway · Dusk + Dawn weekends", "Las Vegas", "vegas", "2027-05-14T19:00:00-07:00", "2027-05-24T05:30:00-07:00", "Dusk May 14–16 · Dawn May 21–23", "https://lasvegas.electricdaisycarnival.com", "edc"),
    ("Cercle Festival", "\U0001F6EB", "Le Bourget Air & Space Museum", "Paris, France", "world", "2027-05-22T14:00:00+02:00", "2027-05-24T23:59:00+02:00", "May 22–24", "https://festival.cercle.io", "cercle"),
    ("Sónar", "\U0001F50A", "Fira Gran Via + waterfront", "Barcelona, Spain", "world", "2027-06-17T12:00:00+02:00", "2027-06-19T23:59:00+02:00", "Jun 17–19", "https://sonar.es", ""),
    ("Glastonbury", "\U0001F37E", "Worthy Farm, Pilton", "Somerset, UK", "world", "2027-06-23T08:00:00+01:00", "2027-06-27T23:59:00+01:00", "Jun 23–27", "https://www.glastonburyfestivals.co.uk", "glastonbury"),
    ("Ultra Europe", "\U0001F3D6️", "Park Mladeži", "Split, Croatia", "world", "2027-07-09T16:00:00+02:00", "2027-07-11T23:59:00+02:00", "Jul 9–11", "https://ultraeurope.com", "ultra"),
    ("UNTOLD", "\U0001F3F0", "Cluj Arena + city centre", "Cluj-Napoca, Romania", "world", "2027-08-05T16:00:00+03:00", "2027-08-08T23:59:00+03:00", "Aug 5–8", "https://untold.com", "untold"),
    ("Creamfields", "\U0001F3A8", "Daresbury Estate · 30 years", "Daresbury, UK", "world", "2027-08-26T12:00:00+01:00", "2027-08-29T23:59:00+01:00", "Aug 26–29", "https://www.creamfields.com", "creamfields"),
    ("Notting Hill Carnival", "\U0001F3B6", "Notting Hill streets · bank-holiday weekend", "London, UK", "world", "2027-08-29T09:00:00+01:00", "2027-08-30T21:00:00+01:00", "Aug 29–30", "https://nhcarnival.org", "carnival"),
    ("Burning Man", "\U0001F525", "Black Rock City", "Black Rock Desert, NV", "world", "2027-08-29T00:00:00-07:00", "2027-09-06T23:59:00-07:00", "Aug 29 – Sep 6", "https://burningman.org", ""),
]

# Single announced dates that no scraper reaches yet (Ibiza is closed Nov-Apr; its club
# calendars are not machine-readable). Each one is a real published listing.
CURATED_EVENTS = [
    # artist/name, venue, type, city, region, local ISO start, url, source
    ("O Beach Ibiza Opening Party", "O Beach Ibiza", "pool", "Sant Antoni, Ibiza", "ibiza",
     "2027-04-30T13:00:00+02:00", "https://ticketsibiza.com/event/o-beach-opening-party-o-beach-2027-04-30/", "Tickets Ibiza"),
]


def curated_events():
    out = []
    for (name, venue, typ, city, region, st, url, src) in CURATED_EVENTS:
        try:
            ts = _iso_ts(st)
        except Exception:
            continue
        out.append({"artist": name, "venue": venue, "type": typ, "city": city, "region": region,
                    "date": st[:10], "ts": ts, "url": url, "src": src})
    return out


def _iso_ts(s):
    return int(datetime.fromisoformat(s).timestamp())

def festivals_json(now=None):
    now = now or int(time.time())
    out = []
    for row in FESTIVALS:
        (name, emoji, where, city, region, st, en, label, url, watch) = row[:10]
        try:
            ts, end_ts = _iso_ts(st), _iso_ts(en)
        except Exception:
            continue
        if end_ts + 6 * 3600 < now:
            continue          # finished: drops off by itself
        ev = {"type": "festival", "artist": name, "emoji": emoji, "venue": where, "city": city,
              "region": region, "date": st[:10], "ts": ts, "end_ts": end_ts, "dateLabel": label,
              "url": url, "watch": watch, "src": "the festival's official site", "mega": True}
        if len(row) > 10 and row[10]:
            ev["nye"] = True      # 3.2: runs through New Year's Eve (the page's NYE filter finds it)
        out.append(ev)
    return out

# 2) LAS VEGAS — No Cover Nightclubs (club + dayclub calendars, slug parser) ──
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
    return {"artist": artist, "venue": vname, "type": vtype, "city": "Las Vegas", "region": "vegas",
            "date": "%04d-%02d-%02d" % (int(year), _VG_MONTHS[mon], int(day)),
            "ts": ts, "url": url, "src": "No Cover Nightclubs"}

# concerts.vegas per-venue pages (date + artist live in the event URL)
VG_CV_SOURCES = [
    ("https://concerts.vegas/venue/msg-sphere-las-vegas/", "Sphere", "sphere"),
    ("https://concerts.vegas/venue/t-mobile-arena-events/", "T-Mobile Arena", "arena"),
    ("https://concerts.vegas/venue/allegiant-stadium-events/", "Allegiant Stadium", "stadium"),
    ("https://concerts.vegas/venue/the-colosseum-at-caesars-palace-events/", "The Colosseum at Caesars Palace", "residency"),
    ("https://concerts.vegas/venue/park-theater-at-park-mgm-events/", "Dolby Live at Park MGM", "residency"),
    ("https://concerts.vegas/venue/dolby-live-at-park-mgm-tickets/", "Dolby Live at Park MGM", "residency"),
    ("https://concerts.vegas/venue/mgm-grand-garden-arena-events/", "MGM Grand Garden Arena", "arena"),
    ("https://concerts.vegas/venue/michelob-ultra-arena-events/", "Michelob Ultra Arena", "arena"),
    ("https://concerts.vegas/venue/the-theater-at-virgin-hotels-las-vegas-events/", "The Theater at Virgin Hotels", "concert"),
    ("https://concerts.vegas/venue/24-oxford-at-virgin-hotels-las-vegas/", "24 Oxford at Virgin Hotels", "concert"),
    ("https://concerts.vegas/venue/resorts-world-theatre/", "Resorts World Theatre", "residency"),
    ("https://concerts.vegas/venue/bakkt-theater-at-planet-hollywood/", "Bakkt Theater at Planet Hollywood", "residency"),
    ("https://concerts.vegas/venue/house-of-blues-las-vegas/", "House of Blues", "concert"),
    ("https://concerts.vegas/venue/encore-theater-at-wynn-las-vegas/", "Encore Theater at Wynn", "residency"),
    ("https://concerts.vegas/venue/bleaulive-theater-at-fontainebleau/", "BleauLive Theater at Fontainebleau", "concert"),
    ("https://concerts.vegas/venue/brooklyn-bowl-las-vegas/", "Brooklyn Bowl", "concert"),
    ("https://concerts.vegas/venue/pearl-concert-theater-at-palms/", "Pearl Theater at Palms", "concert"),
    ("https://concerts.vegas/sports/", "Las Vegas", "sports"),
]
_CV_EVENT_RE = re.compile(r"https://concerts\.vegas/event/[a-z0-9\-]+/?")
_CV_DATE_RE = re.compile(r"-(%s)-([a-z]+)-(\d{1,2})-(\d{4})" % "|".join(_VG_WD))
_CV_CITIES = ["north-las-vegas", "las-vegas", "henderson", "paradise", "enterprise", "summerlin"]
_CV_SPORTS = ("vs", "nhl", "nba", "nfl", "ufc", "wnba", "golden-knights", "raiders", "aces", "stanley-cup", "playoff")
_CV_PER_SRC_MAX = 60

def _cv_parse(url, venue, vtype):
    slug = url.rstrip("/").split("/event/")[-1]
    m = _CV_DATE_RE.search(slug)
    if not m:
        return None
    _wd, mon, day, year = m.groups()
    if mon not in _VG_MONTHS:
        return None
    head = slug[:m.start()]
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
    if any(k in raw_head.split("-") for k in _CV_SPORTS) or any(k in raw_head for k in _CV_SPORTS[5:]):
        t = "sports"
    artist = " ".join(w.capitalize() for w in head.split("-"))
    ts = _cal.timegm((int(year), _VG_MONTHS[mon], int(day), 20, 0, 0, 0, 0, 0))
    return {"artist": artist, "venue": venue, "type": t, "city": city, "region": "vegas",
            "date": "%04d-%02d-%02d" % (int(year), _VG_MONTHS[mon], int(day)),
            "ts": ts, "url": url, "src": "Concerts.Vegas"}

# 3) UNIVERSAL schema.org Event parser (JSON-LD) — Discotech, Eventbrite, venue sites
_LD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)

def _ld_items(data):
    if isinstance(data, list):
        for x in data:
            yield from _ld_items(x)
        return
    if not isinstance(data, dict):
        return
    if isinstance(data.get("@graph"), list):
        yield from _ld_items(data["@graph"])
    typ = data.get("@type", "")
    typ = " ".join(typ) if isinstance(typ, list) else str(typ)
    if typ == "ItemList":
        for el in data.get("itemListElement") or []:
            if isinstance(el, dict):
                yield from _ld_items(el.get("item", el))
        return
    if "Event" in typ:
        yield data

def _jsonld_events(page, default_venue, default_type, default_city="", region=None, src=""):
    """schema.org Event extractor (works on most venue / ticketing pages)."""
    out = []
    for blk in _LD_RE.finditer(page):
        txt = htmllib.unescape(blk.group(1).strip())
        try:
            data = json.loads(txt)
        except Exception:
            continue
        for it in _ld_items(data):
            name, start = it.get("name"), it.get("startDate")
            if not name or not start:
                continue
            s = str(start)
            try:
                if len(s) > 10 and ("+" in s[10:] or "-" in s[10:] or s.endswith("Z")):
                    ts = int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
                else:
                    y, mo, da = (int(x) for x in s[:10].split("-"))
                    ts = _cal.timegm((y, mo, da, 20, 0, 0, 0, 0, 0))
            except Exception:
                continue
            end_ts = None
            if it.get("endDate"):
                try:
                    e = str(it["endDate"])
                    end_ts = int(datetime.fromisoformat(e.replace("Z", "+00:00")).timestamp()) if len(e) > 10 else None
                except Exception:
                    end_ts = None
            loc = it.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            venue = (loc.get("name") if isinstance(loc, dict) else None) or default_venue
            addr = (loc.get("address") if isinstance(loc, dict) else None) or {}
            city = default_city
            if isinstance(addr, dict) and addr.get("addressLocality"):
                city = addr["addressLocality"]
            url = it.get("url") or ""
            offers = it.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict) and offers.get("url"):
                url = offers["url"]
            ev = {"artist": htmllib.unescape(str(name)).strip()[:80], "venue": htmllib.unescape(str(venue))[:80],
                  "type": default_type, "city": city, "date": s[:10], "ts": ts, "url": url, "src": src}
            if end_ts and end_ts > ts:
                ev["end_ts"] = end_ts
            if region:
                ev["region"] = region
            out.append(ev)
    return out

# Eventbrite "nightlife" pages are a mix: keep parties and DJ nights, drop conferences etc.
_PARTY_OK = re.compile(r"\b(party|parties|night|nights|nye|new year|rooftop|boat|yacht|cruise|dj|djs|house|techno|club|"
                       r"rave|edm|hip ?hop|r&b|reggaeton|latin|afro|amapiano|disco|dance|pool|day ?party|brunch party|"
                       r"festival|fest|b2b|soir[ée]e|halloween|bash|takeover|sessions|live|silent disco|perreo|dembow)\b", re.I)
_PARTY_BAD = re.compile(r"\b(conference|networking|seminar|workshop|class|course|webinar|summit|expo|meetup|speed dating|"
                        r"singles|bingo|comedy|stand.?up|teen|kids|church|yoga|fitness|run club|walking tour|wine tasting|"
                        r"business|career|job fair|real estate|investor|crypto|trivia|karaoke|book club|paint|sip and|"
                        r"open mic|women's conference|gala dinner|fundraiser|masterclass|pub crawl|bar crawl|club crawl)\b", re.I)

# 4) 19hz.info electronic-music listings (HTML table, one row per event)
_HZ_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_HZ_TD = re.compile(r"<td[^>]*>(.*?)(?=<td|$)", re.S)
_HZ_TAGS_OK = re.compile(r"house|techno|edm|dnb|drum|jungle|trance|bass|dubstep|disco|afro|amapiano|deep|rave|dance|electro|"
                         r"garage|hardstyle|psy|breaks|melodic|progressive|latin|reggaeton|hip hop|r&b", re.I)

def _strip_tags(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def _hz_parse(page, region_default, metro):
    out = []
    for row in _HZ_ROW.findall(page):
        cells = _HZ_TD.findall(row)
        if len(cells) < 4:
            continue
        sort = _strip_tags(cells[-1])
        m = re.match(r"(\d{4})/(\d{2})/(\d{2})", sort)
        if not m:
            continue
        y, mo, d = (int(x) for x in m.groups())
        title_cell = cells[1]
        link = re.search(r"href='([^']+)'|href=\"([^\"]+)\"", title_cell)
        url = (link.group(1) or link.group(2)) if link else ""
        text = _strip_tags(title_cell)
        name, venue, city = text, "", ""
        mm = re.match(r"(.*?)\s+@\s+(.*?)(?:\s*\(([^)]+)\))?$", text)
        if mm:
            name, venue, city = mm.group(1).strip(), mm.group(2).strip(), (mm.group(3) or "").strip()
        tags = _strip_tags(cells[2]) if len(cells) > 2 else ""
        if not _HZ_TAGS_OK.search(tags + " " + name):
            continue
        if not name or len(name) < 3:
            continue
        reg = region_default if (not city or metro.search(city)) else "world"
        out.append({"artist": name[:80], "venue": venue[:80] or city, "type": "club", "city": city or "",
                    "region": reg, "date": "%04d-%02d-%02d" % (y, mo, d),
                    "ts": _cal.timegm((y, mo, d, 20, 0, 0, 0, 0, 0)) + (7 * 3600 if region_default != "world" else 0),
                    "url": url if url.startswith("http") else "https://19hz.info", "src": "19hz.info"})
    return out

_LA_METRO = re.compile(r"los angeles|hollywood|dtla|downtown|santa monica|venice|pasadena|long beach|inglewood|pomona|"
                       r"glendale|burbank|culver|north hollywood|silver lake|echo park|koreatown|arts district|"
                       r"wilmington|san pedro|commerce|vernon|el monte|\bla\b|weho|west hollywood|chinatown|boyle", re.I)
_MIAMI_METRO = re.compile(r"miami|wynwood|brickell|little haiti|little havana|doral|hialeah|north beach|south beach", re.I)

# Each row: (label, url, kind, default venue, type, default city, region, per-source cap)
CAL_SOURCES = [
    ("Discotech Miami",   "https://www.discotech.me/miami/events/", "ld", "Miami", "club", "Miami", "miami", 40),
    ("19hz Miami",        "https://19hz.info/eventlisting_Miami.php", "hz", "", "club", "Miami", "miami", 40),
    ("19hz Los Angeles",  "https://19hz.info/eventlisting_LosAngeles.php", "hz", "", "club", "Los Angeles", "la", 45),
    ("19hz Bay Area",     "https://19hz.info/eventlisting_BayArea.php", "hz", "", "club", "San Francisco", "world", 15),
    ("19hz Las Vegas",    "https://19hz.info/eventlisting_LasVegas.php", "hz", "", "club", "Las Vegas", "vegas", 15),
    ("19hz Texas",        "https://19hz.info/eventlisting_Texas.php", "hz", "", "club", "Texas", "world", 12),
    ("Eventbrite NYC",    "https://www.eventbrite.com/d/ny--new-york/nightlife/", "eb", "New York", "club", "New York", "nyc", 30),
    ("Eventbrite NYC parties", "https://www.eventbrite.com/d/ny--new-york/parties/", "eb", "New York", "club", "New York", "nyc", 30),
    ("Eventbrite LA",     "https://www.eventbrite.com/d/ca--los-angeles/nightlife/", "eb", "Los Angeles", "club", "Los Angeles", "la", 20),
    ("Eventbrite Miami",  "https://www.eventbrite.com/d/fl--miami/nightlife/", "eb", "Miami", "club", "Miami", "miami", 20),
    ("Eventbrite Las Vegas", "https://www.eventbrite.com/d/nv--las-vegas/nightlife/", "eb", "Las Vegas", "club", "Las Vegas", "vegas", 12),
    ("Eventbrite London", "https://www.eventbrite.com/d/united-kingdom--london/nightlife/", "eb", "London", "club", "London", "world", 20),
    ("Eventbrite Ibiza",  "https://www.eventbrite.com/d/spain--ibiza/parties/", "eb", "Ibiza", "club", "Ibiza", "ibiza", 15),
]
# Optional: any venue's official events page that publishes schema.org Event data.
VG_JSONLD_SOURCES = [
    # ("https://www.example-venue.com/events", "Venue Name", "club"),
]

# 5) Ticketmaster Discovery API — optional (needs a TICKETMASTER_API_KEY secret)
TM_KEY = os.environ.get("TICKETMASTER_API_KEY", "").strip()
TM_API = "https://app.ticketmaster.com/discovery/v2/events.json"
TM_PER_MARKET = 12
TM_DAYS_AHEAD  = 45
TM_MARKETS = [
    ("Las Vegas", "Las Vegas", "US", "club", "vegas"), ("Los Angeles", "Los Angeles", "US", "club", "la"),
    ("Miami", "Miami", "US", "club", "miami"), ("New York", "New York", "US", "club", "nyc"),
    ("Chicago", "Chicago", "US", "concert", "world"), ("Austin", "Austin", "US", "concert", "world"),
    ("New Orleans", "New Orleans", "US", "club", "world"), ("Denver", "Denver", "US", "concert", "world"),
    ("Ibiza", "Ibiza", "ES", "club", "ibiza"), ("Barcelona", "Barcelona", "ES", "club", "world"),
    ("London", "London", "GB", "club", "world"), ("Berlin", "Berlin", "DE", "club", "world"),
    ("Amsterdam", "Amsterdam", "NL", "club", "world"), ("Paris", "Paris", "FR", "concert", "world"),
    ("Tokyo", "Tokyo", "JP", "club", "world"), ("Sydney", "Sydney", "AU", "concert", "world"),
    ("Toronto", "Toronto", "CA", "concert", "world"), ("Mexico City", "Mexico City", "MX", "concert", "world"),
]

def harvest_global_events():
    """Return event dicts from Ticketmaster. NEVER raises; [] without a key or on any problem."""
    if not TM_KEY:
        print("  [TM] no TICKETMASTER_API_KEY set - skipping Ticketmaster")
        return []
    out, seen = [], set()
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    end   = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + TM_DAYS_AHEAD*86400))
    for label, city, cc, etype, region in TM_MARKETS:
        try:
            q = urllib.parse.urlencode({"apikey": TM_KEY, "city": city, "countryCode": cc,
                                        "classificationName": "music", "size": str(TM_PER_MARKET),
                                        "sort": "date,asc", "startDateTime": start, "endDateTime": end})
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
                    else:
                        ts = _cal.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
                    venues = ((ev.get("_embedded") or {}).get("venues") or [{}])
                    venue = (venues[0].get("name") or label).strip()
                    key = (name.lower(), iso[:10], venue.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"artist": name, "venue": venue, "type": etype, "city": label, "region": region,
                                "date": iso[:10], "ts": int(ts), "url": ev.get("url") or "", "src": "Ticketmaster"})
                except Exception:
                    continue
        except Exception as e:
            print(f"  [TM] {label}: {e}")
    print(f"  [TM] harvested {len(out)} events across {len(TM_MARKETS)} markets")
    return out

def _fetch_page(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                           "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                                              "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT + 8) as r:
        return r.read().decode("utf-8", "ignore")

CAL_STATS = {}

def scrape_vegas():
    """Vegas: No Cover club/dayclub calendars + concerts.vegas venue pages. Each source is
    isolated (one failure never empties the calendar); results merge + de-dupe."""
    found = {}
    for cal_url in VG_CALENDARS:
        try:
            html = _fetch_page(cal_url)
        except Exception as e:
            print(f"  [VG WARN] {cal_url}: {e}")
            continue
        n = 0
        for m in _VG_EVENT_RE.finditer(html):
            ev = _vg_parse(m.group(0))
            if ev:
                found[(ev["artist"], ev["venue"], ev["date"])] = ev
                n += 1
        CAL_STATS["No Cover " + cal_url.split("/")[3][:24]] = n
    for url, venue, vtype in VG_CV_SOURCES:
        try:
            html = _fetch_page(url)
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
        CAL_STATS["Concerts.Vegas " + venue] = n
    for url, venue, vtype in VG_JSONLD_SOURCES:
        try:
            html = _fetch_page(url)
        except Exception as e:
            print(f"  [LD WARN] {url}: {e}")
            continue
        for ev in _jsonld_events(html, venue, vtype, "Las Vegas", "vegas", venue):
            found[(ev["artist"], ev["venue"], ev["date"])] = ev
    cutoff = int(time.time()) - 36 * 3600
    return sorted([e for e in found.values() if e["ts"] >= cutoff], key=lambda x: x["ts"])[:300]

def scrape_world():
    """Miami, LA, NYC, London, Ibiza + more: JSON-LD pages, 19hz listings, Eventbrite."""
    out = []
    now = int(time.time())
    horizon = now + 120 * 86400

    def one(row):
        label, url, kind, dvenue, dtype, dcity, region, cap = row
        try:
            page = _fetch_page(url)
        except Exception as e:
            print(f"  [CAL WARN] {label}: {e}")
            return label, []
        if kind == "hz":
            metro = _LA_METRO if region == "la" else (_MIAMI_METRO if region == "miami" else re.compile(re.escape(dcity), re.I))
            evs = _hz_parse(page, region, metro)
        else:
            evs = _jsonld_events(page, dvenue, dtype, dcity, None, label.replace(" parties", ""))
            for e in evs:
                c = (e.get("city") or dcity)
                e["city"] = c
                if region == "nyc" and re.search(r"new york|brooklyn|queens|manhattan|bronx|staten", c, re.I):
                    e["region"] = "nyc"
                elif region == "la" and _LA_METRO.search(c):
                    e["region"] = "la"
                elif region == "miami" and _MIAMI_METRO.search(c + " " + e.get("venue", "")):
                    e["region"] = "miami"
                elif region == "vegas" and re.search(r"las vegas|henderson|paradise", c, re.I):
                    e["region"] = "vegas"
                elif region == "ibiza" and re.search(r"ibiza|eivissa|sant antoni|san antonio|sant josep|santa eul", c, re.I):
                    e["region"] = "ibiza"
                else:
                    e["region"] = "world" if region != "world" else "world"
                if kind == "eb":
                    if not _PARTY_OK.search(e["artist"]) or _PARTY_BAD.search(e["artist"]):
                        e["_drop"] = 1
                if re.search(r"beach|pool|day ?party|dayclub|brunch", e["artist"] + " " + e.get("venue", ""), re.I):
                    e["type"] = "pool"
            evs = [e for e in evs if not e.get("_drop")]
            if region == "ibiza":
                evs = [e for e in evs if e.get("region") == "ibiza"]
        evs = [e for e in evs if now - 12 * 3600 <= e["ts"] <= horizon]
        evs.sort(key=lambda e: e["ts"])
        return label, evs[:cap]

    with ThreadPoolExecutor(max_workers=6) as ex:
        for label, evs in ex.map(one, CAL_SOURCES):
            CAL_STATS[label] = len(evs)
            out.extend(evs)
    return out

def load_prior():
    """Previous feed.json as raw tuples so yesterday's stories persist (fills 'Earlier')."""
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
    _T0 = time.time()
    print(f"[Party Portal Bot 3.2] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Keywords: {len(KEYWORDS)} | Feeds: {len(CULTURE_SOURCES)} | Tabs: {len(TAB_ORDER)}")
    print("  Fetching RSS…")
    raw = fetch_all()
    print(f"  Raw items (fresh): {len(raw)} | feeds returning nothing: "
          + (", ".join(sorted(n for n, c in FEED_STATS.items() if not c)) or "none"))
    prior = load_prior()
    print(f"  Prior items (carried for 'Earlier'): {len(prior)}")
    items = filter_and_dedup(raw + prior)
    multi = sum(1 for i in items if i.get("n", 1) >= 2)
    print(f"  After clean/filter/dedup: {len(items)} ({multi} multi-source)")
    print("  promo/junk filtered: " + (", ".join(f"{k} {v}" for k, v in sorted(_PP_PROMO_LOG.items(), key=lambda kv: -kv[1])) or "none"))
    tabs = {}
    for i in items:
        tabs[i["cat"]] = tabs.get(i["cat"], 0) + 1
    print("  tabs: " + ", ".join(f"{t} {tabs.get(t, 0)}" for t in TAB_ORDER))
    if items:
        with open("feed.json", "w", encoding="utf-8") as f:
            json.dump({"updated": int(time.time()), "tabs": TAB_ORDER, "items": items}, f, ensure_ascii=False, indent=2)
        print(f"[OK] feed.json written — {len(items)} real items")
    else:
        print("[WARN] No real items passed the filters — feed.json left unchanged (no synthetic data).")

    # ── On The Horizon ──
    try:
        print("  Building On The Horizon…")
        try:
            vg = scrape_vegas()
        except Exception as _e:
            print(f"  [VG ERROR] {_e}")
            vg = []
        try:
            world = scrape_world()
        except Exception as _e:
            print(f"  [CAL ERROR] {_e}")
            world = []
        try:
            tm = harvest_global_events()
        except Exception as _ge:
            print(f"  [TM ERROR] {_ge}")
            tm = []
        _now_ts = int(time.time())
        _seen, _clean = set(), []
        for _e in sorted(vg + world + tm + curated_events(), key=lambda x: x.get("ts", 0)):
            if _e.get("ts", 0) < _now_ts - 43200:      # >12h past = expired
                continue
            _k = (re.sub(r"\W+", "", str(_e.get("artist", "")).lower()), _e.get("date", ""),
                  re.sub(r"\W+", "", str(_e.get("venue", "")).lower())[:12])
            if _k in _seen:
                continue
            _seen.add(_k)
            _clean.append(_e)
        fests = festivals_json(_now_ts)
        regions = {}
        for _e in _clean:
            regions[_e.get("region", "world")] = regions.get(_e.get("region", "world"), 0) + 1
        print("  calendar sources: " + ", ".join(f"{k} {v}" for k, v in CAL_STATS.items()))
        print(f"  calendar: {len(_clean)} events + {len(fests)} festivals | by region: "
              + ", ".join(f"{k} {v}" for k, v in sorted(regions.items(), key=lambda kv: -kv[1])))
        if len(_clean) >= 8:
            with open("events.json", "w", encoding="utf-8") as f:
                json.dump({"updated": int(time.time()), "festivals": fests, "events": _clean[:650]},
                          f, ensure_ascii=False, indent=2)
            print(f"[OK] events.json written — {min(len(_clean), 650)} events, {len(fests)} festivals")
        else:
            print(f"[CAL] only {len(_clean)} events parsed — keeping existing events.json (no overwrite)")
    except Exception as e:
        print(f"[CAL ERROR] {e} — events.json left unchanged")

    # ── 3.2 (ORDER-701 C12): health.json - one small report each build; never breaks a build ──
    try:
        def _read_json(path):
            try:
                with open(path, "r", encoding="utf-8") as _hf:
                    return json.load(_hf)
            except Exception:
                return {}
        _ev = _read_json("events.json")
        _chs = _read_json("channels.json").get("channels", [])
        health = {
            "version": "3.2.0",
            "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "build_seconds": round(time.time() - _T0, 1),
            "feeds": {"total": len(CULTURE_SOURCES),
                      "returned_items": sum(1 for _n, _c in FEED_STATS.items() if _c),
                      "empty": sum(1 for _n, _c in FEED_STATS.items() if not _c and _n not in FEED_ERRORS),
                      "failed": len(FEED_ERRORS), "failed_names": sorted(FEED_ERRORS)[:40]},
            "news": {"items": len(items), "multi_outlet": multi,
                     "hot": sum(1 for _i in items if _i.get("hot")),
                     "tabs": {t: tabs.get(t, 0) for t in TAB_ORDER},
                     "promo_filtered": dict(_PP_PROMO_LOG)},
            "calendar": {"events": len(_ev.get("events", [])), "festivals": len(_ev.get("festivals", [])),
                         "events_updated": _ev.get("updated")},
            "channels": {"channels": len(_chs),
                         "videos": sum(len(_c.get("items") or [1]) for _c in _chs),
                         "live": sum(1 for _c in _chs if _c.get("live"))},
        }
        with open("health.json", "w", encoding="utf-8") as _hf:
            json.dump(health, _hf, ensure_ascii=False, indent=1)
        print("[OK] health.json written")
    except Exception as _he:
        print(f"[WARN] health.json not written: {_he}")
    print("[Done]")
