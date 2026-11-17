"""Player points props: per-player projections from this season's ESPN box scores,
distribution width calibrated walk-forward, and matching Winner's Hebrew player names
to ESPN players.

Projection for one player in one game:
    mu = points-per-minute (recency weighted) x expected minutes (recency weighted, faster decay)
         x bias (calibration) x (team's projected points tonight / team's average points)
The team factor ties the player to the game projection (which is anchored to the sharp market),
so pace, opponent defence and blowout risk move player numbers the same way they move the team.
"""
import difflib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta

from . import config
from .pricing import N


# ---------------------------------------------------------------- data
def season_logs(games, boxscore_fn, progress=print):
    """{athlete_id: [dict(start, team, min, pts, dnp)]} from this season's completed games."""
    logs, names, n = defaultdict(list), {}, 0
    cur = [g for g in games if g.get("current")]
    for i, g in enumerate(sorted(cur, key=lambda x: x["start"])):
        box = boxscore_fn(g["id"])
        if not box:
            continue
        n += 1
        if n % 100 == 0:
            progress(f"  box scores: {i + 1}/{len(cur)}")
        for p in box:
            if not p.get("athlete_id") or p["team"] not in (g["home"], g["away"]):
                continue
            logs[p["athlete_id"]].append(dict(start=g["start"], team=p["team"], min=p["min"],
                                              pts=p["pts"], dnp=p["dnp"]))
            names[p["athlete_id"]] = p["name"]
    return logs, names, n


def _w(age_days, half_life):
    return 0.5 ** (max(age_days, 0) / half_life)


def base_projection(log, ref):
    """(mu_points, minutes, ppm, games_played) from games before `ref`; None if too few."""
    played = [x for x in log if x["start"] < ref and not x["dnp"] and x["min"] > 0]
    if len(played) < config.PROP_MIN_GAMES:
        return None
    sw_m = sw_p = sw_mm = sw = 0.0
    for x in played:
        age = (ref - x["start"]).total_seconds() / 86400
        w = _w(age, config.PROP_HALF_LIFE_DAYS)
        sw_m += w * x["min"]; sw_p += w * x["pts"]
        wm = _w(age, config.PROP_MIN_HALF_LIFE_DAYS)
        sw_mm += wm * x["min"]; sw += wm
    if sw_m <= 0 or sw <= 0:
        return None
    ppm, mins = sw_p / sw_m, sw_mm / sw
    return ppm * mins, mins, ppm, len(played)


def team_avg_points(games, ref):
    """Recency-weighted points per game of each team this season (games before ref)."""
    s, w = defaultdict(float), defaultdict(float)
    for g in games:
        if not g.get("current") or g["start"] >= ref:
            continue
        ww = _w((ref - g["start"]).total_seconds() / 86400, config.PROP_HALF_LIFE_DAYS)
        s[g["home"]] += ww * g["hs"]; w[g["home"]] += ww
        s[g["away"]] += ww * g["as"]; w[g["away"]] += ww
    return {t: s[t] / w[t] for t in s if w[t] > 0}


# ---------------------------------------------------------------- calibration
def calibrate(logs):
    """Walk-forward: for every player-game, project from earlier games only.
    Fit sd = a + b*mu (on binned RMS residuals) and an overall bias factor."""
    pairs = []
    for log in logs.values():
        log = sorted(log, key=lambda x: x["start"])
        for x in log:
            if x["dnp"] or x["min"] <= 0:
                continue
            bp = base_projection(log, x["start"])
            if bp and bp[1] >= 10:
                pairs.append((bp[0], x["pts"]))
    cal = dict(config.PROP_DEFAULT_CAL, n=len(pairs))
    if len(pairs) < 400:
        return cal
    smu, spt = sum(m for m, _ in pairs), sum(p for _, p in pairs)
    bias = min(max(spt / smu, 0.9), 1.1) if smu else 1.0
    bins = defaultdict(list)
    for m, p in pairs:
        bins[min(int(m * bias // 4), 8)].append((m * bias, p))
    xs, ys, ws = [], [], []
    for b in bins.values():
        if len(b) < 30:
            continue
        xs.append(sum(m for m, _ in b) / len(b))
        ys.append(math.sqrt(sum((p - m) ** 2 for m, p in b) / len(b)))
        ws.append(len(b))
    if len(xs) >= 3:
        W = sum(ws); mx = sum(w * x for w, x in zip(ws, xs)) / W; my = sum(w * y for w, y in zip(ws, ys)) / W
        vx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
        b_ = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / vx if vx else 0.0
        a_ = my - b_ * mx
        if b_ > 0 and a_ > -2:
            cal.update(a=a_, b=b_)
    cal["bias"] = bias
    return cal


def sd_for(mu, cal):
    return max(cal["a"] + cal["b"] * mu, 2.0)


# ---------------------------------------------------------------- per game
def _status(aid, inj_lists):
    for lst in inj_lists:
        for p in lst:
            if str(p.get("athlete_id")) == str(aid):
                return p.get("status") or ""
    return ""


def project_game(game, proj, logs, names, team_avg, cal, inj_by_team, ref):
    """Players likely to play tonight for both teams, with mu/sd of points."""
    out = []
    for side in ("home", "away"):
        team = game[side]
        team_pts = proj["home_pts"] if side == "home" else proj["away_pts"]
        factor = team_pts / team_avg[team] if team_avg.get(team) else 1.0
        factor = min(max(factor, 0.85), 1.15)
        for aid, log in logs.items():
            if not log:
                continue
            last = max(log, key=lambda x: x["start"])
            if last["team"] != team or (ref - last["start"]) > timedelta(days=21):
                continue
            bp = base_projection([x for x in log if x["team"] == team] or log, ref)
            if not bp or bp[1] < 10:
                continue
            mu = bp[0] * cal["bias"] * factor
            out.append(dict(athlete_id=aid, name=names.get(aid, ""), team=team,
                            mu=round(mu, 2), sd=round(sd_for(mu, cal), 2), min=round(bp[1], 1),
                            ppm=round(bp[2], 3), games=bp[3], status=_status(aid, [inj_by_team.get(team, [])])))
    return out


# ---------------------------------------------------------------- probabilities
def p_side(side, line, mu, sd):
    """P(over/under) for whole-number points. An integer line has an 'exactly' outcome on Winner,
    so over = line+1 or more and under = line-1 or less."""
    if side == "over":
        return 1 - N.cdf((math.floor(line) + 0.5 - mu) / sd)
    return N.cdf((math.ceil(line) - 0.5 - mu) / sd)


# ---------------------------------------------------------------- Hebrew name matching
_HE = {"א": "", "ב": "p", "ג": "g", "ד": "t", "ה": "", "ו": "", "ז": "s", "ח": "", "ט": "t", "י": "",
       "כ": "k", "ך": "k", "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "",
       "פ": "p", "ף": "p", "צ": "s", "ץ": "s", "ק": "k", "ר": "r", "ש": "s", "ת": "t"}
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)\b\.?", re.I)


def _skel_he(s):
    s = re.sub(r"[\"'`׳״.\-]", " ", s or "")
    return [("".join(_HE.get(c, "") for c in w)) for w in s.split() if w]


def _skel_en(s):
    s = _SUFFIX.sub(" ", (s or "").lower())
    s = re.sub(r"[^a-z\s\-']", "", s).replace("-", " ").replace("'", "")
    out = []
    for w in s.split():
        w = re.sub(r"ch(?=[rl])", "k", w)
        w = (w.replace("ph", "p").replace("sch", "s").replace("ch", "s").replace("sh", "s").replace("th", "t")
              .replace("ck", "k").replace("ts", "s").replace("tz", "s"))
        w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k").replace("q", "k").replace("x", "ks")
        w = w.translate(str.maketrans("bvwfdjz", "pppptgs"))
        out.append(re.sub(r"[aeiouyh]", "", w))
    return [w for w in out if w]


def _ratio(a, b):
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def name_score(he, en):
    h, e = _skel_he(he), _skel_en(en)
    if not h or not e:
        return 0.0
    last = _ratio(h[-1], e[-1]) if len(h) == 1 else _ratio("".join(h[1:]), "".join(e[1:]) or e[-1])
    first = _ratio(h[0], e[0]) if len(h) > 1 else last
    return 0.65 * last + 0.35 * first


def _overrides():
    p = config.DATA_DIR / "player_names.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def match(name_he, candidates):
    """Best ESPN player for a Winner Hebrew name among tonight's players of that game, or None."""
    from .teams import norm
    key = norm(name_he)
    want = _overrides().get(key) or config.PLAYER_NAME_SEED.get(key)
    if want:
        for c in candidates:
            if c["name"].lower() == want.lower() or str(c["athlete_id"]) == str(want):
                return c
        return None
    scored = sorted(((name_score(key, c["name"]), c) for c in candidates), key=lambda x: -x[0])
    if not scored or scored[0][0] < 0.72:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None
    return scored[0][1]
