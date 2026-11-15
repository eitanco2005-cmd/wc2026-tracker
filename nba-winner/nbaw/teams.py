"""Hebrew (Winner) team names -> ESPN abbreviations."""
import re

_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")

# (abbr, english, [hebrew keywords — nickname first, then city])
TEAMS = [
    ("ATL", "Atlanta Hawks", ["הוקס", "אטלנטה"]),
    ("BOS", "Boston Celtics", ["סלטיקס", "בוסטון"]),
    ("BKN", "Brooklyn Nets", ["נטס", "ברוקלין"]),
    ("CHA", "Charlotte Hornets", ["הורנטס", "שארלוט"]),
    ("CHI", "Chicago Bulls", ["בולס", "שיקגו"]),
    ("CLE", "Cleveland Cavaliers", ["קאבלירס", "קבלירס", "קאבס", "קליבלנד"]),
    ("DAL", "Dallas Mavericks", ["מאבריקס", "מאווריקס", "דאלאס", "דאלס"]),
    ("DEN", "Denver Nuggets", ["נאגטס", "דנבר"]),
    ("DET", "Detroit Pistons", ["פיסטונס", "דטרויט"]),
    ("GS", "Golden State Warriors", ["ווריורס", "וורירס", "גולדן סטייט"]),
    ("HOU", "Houston Rockets", ["רוקטס", "יוסטון"]),
    ("IND", "Indiana Pacers", ["פייסרס", "אינדיאנה"]),
    ("LAC", "LA Clippers", ["קליפרס"]),
    ("LAL", "Los Angeles Lakers", ["לייקרס"]),
    ("MEM", "Memphis Grizzlies", ["גריזליס", "ממפיס"]),
    ("MIA", "Miami Heat", ["מיאמי"]),
    ("MIL", "Milwaukee Bucks", ["באקס", "מילווקי"]),
    ("MIN", "Minnesota Timberwolves", ["טימברוולבס", "טימברוולבז", "מינסוטה"]),
    ("NO", "New Orleans Pelicans", ["פליקנס", "פליקאנס", "ניו אורלינס"]),
    ("NY", "New York Knicks", ["ניקס", "ניו יורק"]),
    ("OKC", "Oklahoma City Thunder", ["תאנדר", "אוקלהומה"]),
    ("ORL", "Orlando Magic", ["מגיק", "אורלנדו"]),
    ("PHI", "Philadelphia 76ers", ["פילדלפיה", "76"]),
    ("PHX", "Phoenix Suns", ["סאנס", "פיניקס", "פניקס"]),
    ("POR", "Portland Trail Blazers", ["בלייזרס", "פורטלנד"]),
    ("SAC", "Sacramento Kings", ["קינגס", "סקרמנטו"]),
    ("SA", "San Antonio Spurs", ["ספרס", "סאן אנטוניו", "סן אנטוניו"]),
    ("TOR", "Toronto Raptors", ["ראפטורס", "טורונטו"]),
    ("UTAH", "Utah Jazz", ["גאז", "יוטה"]),
    ("WSH", "Washington Wizards", ["וויזארדס", "ויזארדס", "וושינגטון"]),
]

ABBR_TO_NAME = {a: e for a, e, _ in TEAMS}
ABBR_TO_HE = {}


def norm(s: str) -> str:
    s = _BIDI.sub("", s or "")
    s = s.replace("'", "").replace("׳", "").replace("`", "").replace('"', "").replace("״", "")
    return re.sub(r"\s+", " ", s).strip()


def to_abbr(hebrew_name: str):
    n = norm(hebrew_name)
    best = None
    for abbr, _, kws in TEAMS:
        for kw in kws:
            if kw in n and (best is None or len(kw) > best[1]):
                best = (abbr, len(kw))
    return best[0] if best else None
