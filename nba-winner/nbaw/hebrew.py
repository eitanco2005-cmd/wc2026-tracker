"""Plain-Hebrew names and bet descriptions."""
FULL = {
    "ATL": "אטלנטה הוקס", "BOS": "בוסטון סלטיקס", "BKN": "ברוקלין נטס", "CHA": "שארלוט הורנטס",
    "CHI": "שיקגו בולס", "CLE": "קליבלנד קבלירס", "DAL": "דאלאס מאבריקס", "DEN": "דנבר נאגטס",
    "DET": "דטרויט פיסטונס", "GS": "גולדן סטייט ווריורס", "HOU": "יוסטון רוקטס",
    "IND": "אינדיאנה פייסרס", "LAC": "לוס אנג'לס קליפרס", "LAL": "לוס אנג'לס לייקרס",
    "MEM": "ממפיס גריזליס", "MIA": "מיאמי היט", "MIL": "מילווקי באקס",
    "MIN": "מינסוטה טימברוולבס", "NO": "ניו אורלינס פליקנס", "NY": "ניו יורק ניקס",
    "OKC": "אוקלהומה סיטי ת'אנדר", "ORL": "אורלנדו מג'יק", "PHI": "פילדלפיה 76",
    "PHX": "פיניקס סאנס", "POR": "פורטלנד טרייל בלייזרס", "SAC": "סקרמנטו קינגס",
    "SA": "סאן אנטוניו ספרס", "TOR": "טורונטו ראפטורס", "UTAH": "יוטה ג'אז",
    "WSH": "וושינגטון וויזארדס",
}
PER = {"FG": "במשחק כולו (כולל הארכות)", "H1": "במחצית הראשונה", "Q1": "ברבע הראשון"}
PER_SHORT = {"FG": "משחק מלא", "H1": "מחצית ראשונה", "Q1": "רבע ראשון"}
CONF = {"A": "גבוה", "B": "בינוני", "C": "נמוך", "P": "נמוך (הימור שחקן)"}


def team(a):
    return FULL.get(a, a)


def game(home, away):
    return f"{team(away)} נגד {team(home)}"


def _n(x):
    x = float(x)
    return f"{x:g}"


def describe(b):
    """(plain sentence, what to tap in Winner)."""
    k, per, side, line = b["kind"], b["period"], b["side"], float(b["line"])
    if k in ("spread", "ml"):
        t = team(b["home"] if side == "home" else b["away"])
        if k == "ml" or line == 0:
            s = f"{t} מנצחת {PER[per]}"
        elif line < 0:
            s = f"{t} מנצחת בהפרש של יותר מ-{_n(-line)} נקודות {PER[per]}"
        else:
            s = f"{t} לא מפסידה ביותר מ-{_n(line)} נקודות {PER[per]}"
        hint = f"הימור יתרון – {PER_SHORT[per]} ← {t} ({'+' if line > 0 else ''}{_n(line)})"
    elif k == "total":
        w = "מעל" if side == "over" else "מתחת"
        s = f"{'יותר' if side == 'over' else 'פחות'} מ-{_n(line)} נקודות ביחד {PER[per]}"
        hint = f"מעל/מתחת נקודות – {PER_SHORT[per]} ← {w} {_n(line)}"
    elif k == "player_points":
        who = b.get("player") or ""
        w = "מעל" if side == "over" else "מתחת"
        if line == int(line):   # whole line: Winner also has "exactly", so over/under exclude it
            s = (f"{who} קולע {int(line) + 1} נקודות או יותר {PER[per]}" if side == "over"
                 else f"{who} קולע {int(line) - 1} נקודות או פחות {PER[per]}")
        else:
            s = f"{who} קולע {'יותר' if side == 'over' else 'פחות'} מ-{_n(line)} נקודות {PER[per]}"
        hint = f"מעל/מתחת נקודות שחקן ← {who} – {w} {_n(line)}"
    else:
        t = team(b["team"])
        w = "מעל" if side == "over" else "מתחת"
        s = f"{t} קולעת {'יותר' if side == 'over' else 'פחות'} מ-{_n(line)} נקודות {PER[per]}"
        hint = f"מעל/מתחת נקודות – {t} ← {w} {_n(line)}"
    return s, hint
