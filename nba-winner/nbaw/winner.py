"""Fetch and parse the Winner (winner.co.il) NBA line."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from . import config
from .teams import norm, to_abbr, _BIDI

LINE_URL = "https://www.winner.co.il/api/v2/publicapi/GetCMobileLine?lineChecksum=0"
HOME_URL = "https://www.winner.co.il/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


# ---------------------------------------------------------------- fetching
def _fetch_playwright(headless=True) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless,
                                    args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="he-IL", user_agent=UA, timezone_id="Asia/Jerusalem",
                                  viewport={"width": 1366, "height": 800})
        page = ctx.new_page()
        resp = page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90_000)
        print(f"    winner home: HTTP {resp.status if resp else '?'}")
        txt = ""
        for attempt in range(4):
            page.wait_for_timeout(6000)
            res = page.evaluate(
                "async (u) => { const r = await fetch(u); return [r.status, await r.text()]; }",
                LINE_URL.replace("https://www.winner.co.il", ""))
            print(f"    winner line attempt {attempt + 1}: HTTP {res[0]}, {len(res[1])} bytes, starts {res[1][:80]!r}")
            if res[0] == 200 and res[1].lstrip().startswith("{"):
                txt = res[1]
                break
            page.reload(wait_until="domcontentloaded")
        browser.close()
    return json.loads(txt)


def _fetch_requests() -> dict:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "he-IL,he;q=0.9",
                      "Referer": HOME_URL, "Accept": "application/json"})
    s.get(HOME_URL, timeout=config.HTTP_TIMEOUT)
    r = s.get(LINE_URL, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_line(winner_file=None, show_browser=False) -> list[dict]:
    """Returns the raw NBA markets list."""
    if winner_file:
        data = json.loads(open(winner_file, encoding="utf-8").read())
    else:
        errors = []
        data = None
        for fn in (lambda: _fetch_playwright(headless=not show_browser), _fetch_requests):
            try:
                data = fn()
                if data.get("markets"):
                    break
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e)[:200])
        if not data or not data.get("markets"):
            raise RuntimeError("Could not load Winner line:\n" + "\n".join(errors))
    markets = data["markets"] if isinstance(data, dict) and "markets" in data else data
    nba = [m for m in markets if (m.get("league") or "").strip().upper() == "NBA"]
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo(config.TZ)).strftime("%Y%m%d_%H%M")
    (config.DATA_DIR / f"winner_nba_{stamp}.json").write_text(
        json.dumps({"markets": nba}, ensure_ascii=False), encoding="utf-8")
    return nba


# ---------------------------------------------------------------- parsing
_SPREAD = re.compile(r"^(.*?)\(\s*([+-]?\s*\d+(?:\.\d+)?)\s*\)\s*$")
_TOTAL = re.compile(r"^(מעל|מתחת|בדיוק)\s*([\d.]+)")


def _period(mp: str):
    if "רבע ראשון" in mp:
        return "Q1"
    if "מחצית ראשונה" in mp:
        return "H1"
    if "כולל הארכות" in mp:
        return "FG"
    return None


def _start(m) -> datetime | None:
    try:
        d, h = str(m["e_date"]), str(m["m_hour"]).zfill(4)
        return datetime(2000 + int(d[:2]), int(d[2:4]), int(d[4:6]), int(h[:2]), int(h[2:]),
                        tzinfo=ZoneInfo(config.TZ))
    except Exception:  # noqa: BLE001
        return None


def _disp(s):
    return re.sub(r"\s+", " ", _BIDI.sub("", s or "")).strip()


def parse(raw: list[dict]) -> list[dict]:
    out = []
    for m in raw:
        desc = norm(m.get("desc", ""))
        if " - " not in desc:
            continue  # futures / specials
        home_he, away_he = [x.strip() for x in desc.split(" - ", 1)]
        home, away = to_abbr(home_he), to_abbr(away_he)
        if not home or not away:
            continue
        mp = norm(m.get("mp", ""))
        period = _period(mp)
        base = dict(mid=m.get("mId"), eid=m.get("eId"), home=home, away=away,
                    home_he=_disp(m.get('desc','').split(' - ')[0]), away_he=_disp(m.get('desc','').split(' - ',1)[-1]), start=_start(m), mp=mp,
                    period=period, flag=m.get("mSTRem"), outcomes=[])
        outs = m.get("outcomes", [])

        if mp.startswith("הימור יתרון") and period:
            base["kind"] = "spread"
            for o in outs:
                mm = _SPREAD.match(norm(o["desc"]))
                if not mm:
                    break
                ab = to_abbr(mm.group(1))
                side = "home" if ab == home else "away" if ab == away else None
                if not side:
                    break
                base["outcomes"].append(dict(label=_disp(o["desc"]), side=side,
                                             line=float(mm.group(2).replace(" ", "")),
                                             odds=float(o["price"])))
        elif mp.startswith("מעל/מתחת נקודות שחקן"):
            if period != "FG":
                continue
            base["kind"], base["team"] = "player_points", None
            for o in outs:
                d = norm(o["desc"])
                if " - " not in d:
                    continue
                name, rest = d.rsplit(" - ", 1)
                mm = _TOTAL.match(rest.strip())
                if not mm or mm.group(1) == "בדיוק":
                    continue
                if base.get("player_he") not in (None, name.strip()):
                    continue  # one player per market
                base["player_he"] = name.strip()
                base["player_disp"] = _disp(o["desc"]).rsplit(" - ", 1)[0].strip()
                base["outcomes"].append(dict(label=_disp(o["desc"]),
                                             side="over" if mm.group(1) == "מעל" else "under",
                                             line=float(mm.group(2)), odds=float(o["price"])))
        elif mp.startswith("מעל/מתחת נקודות") and period:
            parts = [p.strip() for p in mp.split(" - ")]
            team = to_abbr(parts[1]) if len(parts) == 3 else None
            if team and team not in (home, away):
                continue
            base["kind"] = "team_total" if team else "total"
            base["team"] = team
            for o in outs:
                mm = _TOTAL.match(norm(o["desc"]))
                if not mm or mm.group(1) == "בדיוק":
                    continue
                base["outcomes"].append(dict(label=_disp(o["desc"]),
                                             side="over" if mm.group(1) == "מעל" else "under",
                                             line=float(mm.group(2)), odds=float(o["price"])))
        elif period == "FG" and len(outs) == 2 and all(
                to_abbr(o["desc"]) in (home, away) and "(" not in o["desc"] for o in outs) \
                and ("מנצח" in mp or "1X2" in mp or "זוכה" in mp):
            base["kind"] = "ml"
            for o in outs:
                ab = to_abbr(o["desc"])
                base["outcomes"].append(dict(label=_disp(o["desc"]),
                                             side="home" if ab == home else "away",
                                             line=0.0, odds=float(o["price"])))
        else:
            continue  # unsupported (first basket, HT/FT, 3PT, race-to)
        if len(base["outcomes"]) == 2:
            out.append(base)
    return out
