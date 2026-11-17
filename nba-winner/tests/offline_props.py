"""Offline test for player points props: capture decode, Hebrew name matching, probabilities,
grading, and an end-to-end sheet -> picks -> settle run on synthetic box scores."""
import json
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "_out_props"

from nbaw import config, espn  # noqa: E402

shutil.rmtree(OUT, ignore_errors=True)
config.DATA_DIR = OUT / "data"
config.REPORTS_DIR = OUT / "reports"
config.CACHE_DIR = OUT / "cache"
config.ROOT = OUT            # site index.html goes here, not over the real one

from nbaw import compact, engine, players, tracker, winner  # noqa: E402
from nbaw.hebrew import describe  # noqa: E402
from nbaw.teams import TEAMS  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# ---------------------------------------------------------------- 1. capture -> parse (real record)
rec = "40874965|MIN-POR|2611180259|FGPדני אבדיה|o26:1.75,u26:1.75"
wm = winner.parse(compact.decode(rec))
check(len(wm) == 1 and wm[0]["kind"] == "player_points", "Winner prop decodes to a player_points market")
m0 = wm[0]
check(m0["player_he"] == "דני אבדיה" and [o["side"] for o in m0["outcomes"]] == ["over", "under"]
      and m0["outcomes"][0]["line"] == 26.0, "player name, sides and line parsed")
raw_exact = [{"mId": 1, "desc": "מינסוטה טימברוולבס - פורטלנד טרייל בלייזרס",
              "mp": "מעל/מתחת נקודות שחקן - כולל הארכות אם יהיו", "league": "NBA", "e_date": 261118,
              "m_hour": "0259", "outcomes": [{"desc": "דני אבדיה - מעל 26", "price": "1.75"},
                                             {"desc": "דני אבדיה - בדיוק 26", "price": "9.50"},
                                             {"desc": "דני אבדיה - מתחת 26", "price": "1.75"}]}]
w2 = winner.parse(raw_exact)
check(len(w2) == 1 and len(w2[0]["outcomes"]) == 2, "raw 3-way Winner prop -> 'exactly' dropped")
old_total = winner.parse(compact.decode("39015530|MIN-POR|2611180259|FGO|o227.5:1.80,u227.5:1.70"))
check(old_total[0]["kind"] == "total", "game totals still parse as totals")

# ---------------------------------------------------------------- 2. name matching
C = [dict(name=n, athlete_id=str(i), team="X") for i, n in enumerate(
    ["Deni Avdija", "Donovan Clingan", "Jerami Grant", "Shaedon Sharpe", "Anthony Edwards",
     "Rudy Gobert", "Julius Randle", "Jaden McDaniels", "Naz Reid", "Toumani Camara"])]
for he, en in [("דני אבדיה", "Deni Avdija"), ("אנתוני אדוארדס", "Anthony Edwards"), ("רודי גובר", "Rudy Gobert"),
               ("ג'רמי גרנט", "Jerami Grant"), ("ג'וליוס רנדל", "Julius Randle"), ("שיידון שארפ", "Shaedon Sharpe"),
               ("נאז ריד", "Naz Reid"), ("טומאני קמארה", "Toumani Camara"), ("ג'יידן מקדניאלס", "Jaden McDaniels")]:
    got = players.match(he, C)
    check(got is not None and got["name"] == en, f"match {he} -> {got['name'] if got else None}")
check(players.match("לברון ג'יימס", C) is None, "no match for a player who isn't in the game")

# ---------------------------------------------------------------- 3. probabilities / grading / text
po, pu = players.p_side("over", 26, 26, 7), players.p_side("under", 26, 26, 7)
check(abs(po - pu) < 1e-9 and po + pu < 1, "integer line: over/under symmetric, 'exactly' mass excluded")
check(abs(players.p_side("over", 26.5, 26.5, 7) - 0.5) < 1e-9, "half line at the mean = 50%")
leg = dict(athlete_id="7", line=26, side="over")
check(tracker._grade_prop(leg, [dict(athlete_id="7", pts=26, dnp=False)]) == "L", "exactly on the line loses")
check(tracker._grade_prop(leg, [dict(athlete_id="7", pts=27, dnp=False)]) == "W", "27 beats over 26")
check(tracker._grade_prop(dict(leg, side="under"), [dict(athlete_id="7", pts=25, dnp=False)]) == "W", "25 beats under 26")
check(tracker._grade_prop(leg, [dict(athlete_id="7", pts=0, dnp=True)]) == "P", "did not play -> void")
title, hint = describe(dict(kind="player_points", period="FG", side="over", line=26, player="דני אבדיה"))
check("27 נקודות או יותר" in title and "דני אבדיה" in hint, f"Hebrew text: {title} | {hint}")

# ---------------------------------------------------------------- 4. end-to-end on synthetic data
NOW = datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc)
random.seed(11)
ABBRS = [t[0] for t in TEAMS]
TRUE = {a: random.gauss(0, 5) for a in ABBRS}
OFF = {a: random.gauss(0, 3) for a in ABBRS}
SHARE = [.24, .19, .15, .12, .10, .08, .06, .04, .02]
MINS = [36, 34, 32, 30, 28, 22, 18, 14, 10]
BOX = {}


def synth():
    games = []
    for season, start, n_days, cur in ((2026, datetime(2025, 10, 21, 23, tzinfo=timezone.utc), 170, False),
                                       (2027, datetime(2026, 10, 20, 23, tzinfo=timezone.utc), 26, True)):
        for d in range(n_days):
            day = start + timedelta(days=d)
            teams = random.sample(ABBRS, 14)
            for i in range(0, 14, 2):
                h, a = teams[i], teams[i + 1]
                m = random.gauss(2.5 + TRUE[h] - TRUE[a], 12); t = random.gauss(226 + 2 * (OFF[h] + OFF[a]), 17)
                hs, as_ = round((t + m) / 2), round((t - m) / 2)
                gid = f"{season}{d}{i}"
                q = lambda x: [x // 4] * 3 + [x - 3 * (x // 4)]  # noqa: E731
                games.append(dict(id=gid, start=day, season=season, stype=2, home=h, away=a, completed=True,
                                  neutral=False, hs=float(hs), hq=q(hs), aq=q(as_), current=cur) | {"as": float(as_)})
                if cur:
                    box = []
                    for team, pts in ((h, hs), (a, as_)):
                        for k, (sh, mn) in enumerate(zip(SHARE, MINS)):
                            dnp = random.random() < 0.05
                            mu = sh * pts
                            box.append(dict(team=team, athlete_id=f"{team}{k}", name=f"Player {team} {k}",
                                            min=0.0 if dnp else float(max(4, round(random.gauss(mn, 3)))),
                                            pts=0.0 if dnp else float(max(0, round(random.gauss(mu, 1.2 * mu ** 0.5)))),
                                            dnp=dnp))
                    BOX[gid] = box
    return games


espn.history = lambda today, progress=print: synth()
espn.todays_games = lambda now: [espn.parse_event(e) for e in json.load(open(FX / "espn_today.json"))["events"]]
espn.injuries = lambda: {"Phoenix Suns": [dict(name="Player PHX 1", athlete_id="PHX1", status="out", comment="")]}
espn.athlete_stats = lambda aid: None
espn.boxscore = lambda gid, use_cache=True: BOX.get(gid)
espn.now_utc = lambda: NOW

import run  # noqa: E402

run.cmd_sheet(NOW)
snap = json.loads((config.DATA_DIR / "projections.json").read_text(encoding="utf-8"))
g = next(x for x in snap["games"] if x["game"]["id"] == "401909986")       # LAL @ PHX
pl = {p["athlete_id"]: p for p in g["proj"]["players"]}
check(snap.get("prop_cal") and snap["prop_cal"]["n"] > 400, f"calibration ran: {snap.get('prop_cal')}")
check("PHX0" in pl and "LAL0" in pl and len(pl) <= 18, f"projections for both rosters ({len(pl)} players)")
check(pl["PHX1"]["status"] == "out", "injury status attached")
star = pl["PHX0"]
print(f"     PHX0 mu={star['mu']} sd={star['sd']} min={star['min']}")

# Winner board for that game: a value prop on PHX0, a prop on an injured player, an unknown player
line0 = float(round(star["mu"]) - 4)
(config.DATA_DIR / "player_names.json").write_text(json.dumps(
    {"שחקן ראשון": "Player PHX 0", "שחקן פצוע": "Player PHX 1"}, ensure_ascii=False), encoding="utf-8")
txt = ";".join([
    "1|PHX-LAL|2611152300|FGS|PHX+1.5:1.75,LAL-1.5:1.85",
    "2|PHX-LAL|2611152300|FGO|o228.5:1.75,u228.5:1.75",
    f"3|PHX-LAL|2611152300|FGPשחקן ראשון|o{line0:g}:1.85,u{line0:g}:1.85",
    f"4|PHX-LAL|2611152300|FGPשחקן פצוע|o{pl['PHX1']['mu'] - 4:.0f}:1.85,u{pl['PHX1']['mu'] - 4:.0f}:1.85",
    "5|PHX-LAL|2611152300|FGPמישהו אחר|o20:1.85,u20:1.85"])
wf = config.DATA_DIR / "w.json"
wf.write_text(json.dumps({"markets": compact.decode(txt)}, ensure_ascii=False), encoding="utf-8")
sys.argv = ["run.py", "picks", "--winner-file", str(wf), "--no-open"]
run.main()
rows = tracker.load()
props = [r for r in rows if json.loads(r["legs_json"])[0]["kind"] == "player_points"]
check(len(props) == 1, f"one prop ticket logged ({len(props)})")
if props:
    lg = json.loads(props[0]["legs_json"])[0]
    check(lg["athlete_id"] == "PHX0" and lg["side"] == "over", "the value side on the healthy star")
    check(f"{int(line0) + 1} נקודות או יותר" in props[0]["title"], f"site title: {props[0]['title']}")
html = (OUT / "reports" / "latest.html").read_text(encoding="utf-8")
check("שחקן ראשון" in html, "prop shown on the site")
full = (OUT / "reports" / "latest_full.html").read_text(encoding="utf-8")
check("מישהו אחר" in full, "unmatched player reported as a warning")

# settle: star scores line0+3 -> win
ev_ = {"id": "401909986"}
espn.scoreboard = lambda d, use_cache=False: {"events": [ev_]}
espn.parse_event = lambda e: dict(id="401909986", completed=True, home="PHX", away="LAL", hs=110.0, hq=[28, 27, 28, 27],
                                  aq=[25, 25, 25, 25]) | {"as": 100.0}
espn.boxscore = lambda gid, use_cache=True: [dict(athlete_id="PHX0", pts=line0 + 3, dnp=False, team="PHX", min=35)]
n, _ = tracker.settle()
r = next(x for x in tracker.load() if x["id"] == props[0]["id"]) if props else None
check(r is not None and r["result"] == "W" and float(r["pnl"]) > 0, f"prop graded: {r and (r['result'], r['pnl'])}")

print("\n" + ("ALL OK" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
