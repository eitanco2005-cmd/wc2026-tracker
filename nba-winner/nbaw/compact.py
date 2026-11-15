"""Decode the compact Winner line captured in the browser into Winner-format markets."""
from .teams import ABBR_TO_HE

FG = "כולל הארכות אם יהיו"
PER = {"FG": FG, "H1": "מחצית ראשונה", "Q1": "רבע ראשון"}


def decode(text, fix=None):
    fix = fix or {}
    out = []
    for rec in filter(None, text.strip().split(";")):
        mid, teams, dh, code, outs = rec.split("|")
        home, away = teams.split("-")
        game_fix = fix.get(teams, {})
        home, away = game_fix.get(home, home), game_fix.get(away, away)
        per, kind = code[:2], code[2]
        H, A = ABBR_TO_HE[home], ABBR_TO_HE[away]
        if kind == "S":
            mp = f"הימור יתרון - {PER[per]}"
        elif kind == "O":
            mp = f"מעל/מתחת נקודות - {PER[per]}"
        else:
            t = game_fix.get(code[3:], code[3:])
            mp = f"מעל/מתחת נקודות - {ABBR_TO_HE[t]} - {FG}"
        o = []
        for x in outs.split(","):
            sel, price = x.split(":")
            if kind == "S":
                ab = sel.rstrip("0123456789.+-")
                line = sel[len(ab):]
                ab = game_fix.get(ab, ab)
                o.append({"desc": f"{ABBR_TO_HE[ab]} ({line})", "price": price})
            else:
                o.append({"desc": ("מעל " if sel[0] == "o" else "מתחת ") + sel[1:], "price": price})
        out.append({"mId": int(mid), "desc": f"{H} - {A}", "mp": mp, "league": "NBA",
                    "e_date": int(dh[:6]), "m_hour": dh[6:], "mSTRem": "", "outcomes": o})
    return out
