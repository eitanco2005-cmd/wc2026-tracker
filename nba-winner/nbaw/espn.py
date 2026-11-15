"""ESPN public data: results history, today's schedule + DraftKings lines, injuries, player stats."""
import json
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import config
from .teams import ABBR_TO_NAME

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0"


def _get(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def _cache_path(name):
    p = config.CACHE_DIR / "espn"
    p.mkdir(parents=True, exist_ok=True)
    return p / name


def scoreboard(d: date, use_cache=True):
    """Raw scoreboard for one US date. Completed past days are cached forever."""
    key = d.strftime("%Y%m%d")
    cp = _cache_path(f"sb_{key}.json")
    if use_cache and cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    data = _get(f"{SITE}/scoreboard", {"dates": key, "limit": 100})
    if data is None:
        return {"events": []}
    evs = data.get("events", [])
    final = all(e["competitions"][0]["status"]["type"].get("completed") for e in evs)
    if d < date.today() - timedelta(days=1) and final:
        cp.write_text(json.dumps(data), encoding="utf-8")
    return data


# ---------------------------------------------------------------- parsing
def _linescores(c):
    return [float(x.get("value", 0) or 0) for x in c.get("linescores", [])]


def parse_event(e):
    comp = e["competitions"][0]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    if "home" not in teams or "away" not in teams:
        return None
    h, a = teams["home"], teams["away"]
    ha, aa = h.get("team", {}).get("abbreviation"), a.get("team", {}).get("abbreviation")
    if not ha or not aa:
        return None  # TBD / All-Star placeholder
    st = comp["status"]["type"]
    g = dict(
        id=e["id"], start=datetime.fromisoformat(e["date"].replace("Z", "+00:00")),
        season=e.get("season", {}).get("year"), stype=e.get("season", {}).get("type"),
        home=ha, away=aa,
        completed=bool(st.get("completed")), state=st.get("state"),
        neutral=bool(comp.get("neutralSite")),
    )
    if g["completed"]:
        g["hs"], g["as"] = float(h.get("score") or 0), float(a.get("score") or 0)
        g["hq"], g["aq"] = _linescores(h), _linescores(a)
    g["odds"] = parse_odds(comp.get("odds") or [])
    return g


def parse_odds(odds_list):
    """DraftKings (via ESPN) -> dict with spread/total/ml decimal prices."""
    from .pricing import american_to_decimal as a2d
    if not odds_list:
        return None
    o = odds_list[0]
    res = {"provider": o.get("provider", {}).get("name"),
           "spread": o.get("spread"), "total": o.get("overUnder")}
    try:
        ps = o["pointSpread"]
        res["spread_home_line"] = float(ps["home"]["close"]["line"])
        res["spread_home_odds"] = a2d(ps["home"]["close"]["odds"])
        res["spread_away_odds"] = a2d(ps["away"]["close"]["odds"])
        res["spread_open_home_line"] = float(ps["home"].get("open", {}).get("line", "nan"))
    except (KeyError, TypeError, ValueError):
        pass
    try:
        t = o["total"]
        res["total_line"] = float(str(t["over"]["close"]["line"]).lstrip("ou"))
        res["over_odds"] = a2d(t["over"]["close"]["odds"])
        res["under_odds"] = a2d(t["under"]["close"]["odds"])
        res["total_open_line"] = float(str(t["over"].get("open", {}).get("line", "nan")).lstrip("ou"))
    except (KeyError, TypeError, ValueError):
        pass
    try:
        ml = o["moneyline"]
        res["ml_home"] = a2d(ml["home"]["close"]["odds"])
        res["ml_away"] = a2d(ml["away"]["close"]["odds"])
    except (KeyError, TypeError, ValueError):
        pass
    return res


# ---------------------------------------------------------------- history
def season_start(today: date) -> date:
    y = today.year if today.month >= 8 else today.year - 1
    return date(y, 10, 1)


def history(today: date, progress=print):
    """All completed regular-season + playoff games from last season and this season."""
    cur = season_start(today)
    prev = date(cur.year - 1, 10, 1)
    days = []
    d = prev
    while d < today:
        if not (7 <= d.month <= 9):
            days.append(d)
        d += timedelta(days=1)
    games, fetched = [], 0
    for i, d in enumerate(days):
        cached = _cache_path(f"sb_{d:%Y%m%d}.json").exists()
        sb = scoreboard(d)
        if not cached:
            fetched += 1
            if fetched % 25 == 0:
                progress(f"  ESPN history: {i + 1}/{len(days)} days")
        for e in sb.get("events", []):
            g = parse_event(e)
            if g and g["completed"] and g["stype"] in (2, 3) \
                    and g["home"] in ABBR_TO_NAME and g["away"] in ABBR_TO_NAME:
                g["current"] = d >= cur
                games.append(g)
    return games


def todays_games(now_utc: datetime):
    """Upcoming games in the next ~36h (ESPN dates are US-local)."""
    out = {}
    base = (now_utc - timedelta(hours=8)).date()
    for d in (base, base + timedelta(days=1)):
        for e in scoreboard(d, use_cache=False).get("events", []):
            g = parse_event(e)
            if g and not g["completed"]:
                out[g["id"]] = g
    return list(out.values())


# ---------------------------------------------------------------- injuries
def injuries():
    data = _get(f"{SITE}/injuries") or {}
    res = {}
    for t in data.get("injuries", []):
        lst = []
        for inj in t.get("injuries", []):
            a = inj.get("athlete", {})
            aid = None
            for l in a.get("links", []):
                href = l.get("href", "")
                if "/id/" in href:
                    aid = href.split("/id/")[1].split("/")[0]
                    break
            lst.append(dict(name=a.get("displayName"), athlete_id=aid,
                            status=(inj.get("status") or "").lower(),
                            comment=inj.get("shortComment", "")))
        res[t.get("displayName")] = lst
    return res


_ath_cache = {}


def athlete_stats(aid):
    if not aid:
        return None
    if aid in _ath_cache:
        return _ath_cache[aid]
    data = _get(f"{WEB}/athletes/{aid}/overview")
    stats = None
    try:
        s = data["statistics"]
        names = s["names"]
        for sp in s["splits"]:
            if sp["displayName"] == "Regular Season":
                stats = {n: float(v) for n, v in zip(names, sp["stats"])}
                break
    except (TypeError, KeyError, ValueError):
        pass
    _ath_cache[aid] = stats
    return stats


def now_utc():
    return datetime.now(timezone.utc)
