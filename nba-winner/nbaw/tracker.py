"""Log recommended bets and grade them against ESPN results."""
import csv
import json
from datetime import timedelta

from . import config, espn

FIELDS = ["id", "created", "type", "game_ids", "desc", "legs_json", "odds", "p", "ev",
          "stake", "result", "pnl", "title", "hint", "tier", "first_start"]


def _path():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return config.DATA_DIR / "picks.csv"


def load():
    p = _path()
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as f:
        return [{k: (r.get(k) or "") for k in FIELDS} for r in csv.DictReader(f)]


def save(rows):
    with _path().open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _leg(b):
    from .hebrew import describe, game
    title, hint = describe(b)
    return dict(game_id=b["game_id"], kind=b["kind"], period=b["period"], side=b["side"],
                team=b["team"], line=b["line"], odds=b["odds"], home=b["home"], away=b["away"],
                label=b["label"], start=b["start"].isoformat(), title=title, hint=hint,
                game=game(b["home"], b["away"]), tier=b["tier"], p=b["p"], anomaly=b.get("anomaly") or "",
                **({"player": b.get("player"), "athlete_id": b.get("athlete_id"), "player_en": b.get("player_en")}
                   if b["kind"] == "player_points" else {}))


def log(now, singles, parlays):
    """Today's tickets replace any earlier, not-yet-started pending tickets."""
    from datetime import datetime
    rows = load()
    keep = []
    for r in rows:
        if r["result"]:
            keep.append(r); continue
        try:
            first = min(datetime.fromisoformat(l["start"]) for l in json.loads(r["legs_json"]))
        except Exception:  # noqa: BLE001
            keep.append(r); continue
        if first <= now:
            keep.append(r)        # already running -> it stands
    rows = keep
    existing = {r["id"] for r in rows}
    for b, stake in singles:
        pid = f"S-{b['winner_mid']}-{b['side']}-{b['line']}"
        if pid in existing:
            continue
        leg = _leg(b)
        rows.append(dict(id=pid, created=now.isoformat(), type="single", game_ids=b["game_id"],
                         desc=f"{b['away']}@{b['home']} {b['label']} ({b['market']})",
                         legs_json=json.dumps([leg], ensure_ascii=False), odds=f"{b['odds']:.2f}",
                         p=f"{b['p']:.4f}", ev=f"{b['ev']:.4f}", stake=stake, result="", pnl="",
                         title=leg["title"], hint=leg["hint"], tier=b["tier"], first_start=leg["start"]))
    for par, stake in parlays:
        pid = "P-" + "_".join(f"{l['winner_mid']}{l['side'][0]}" for l in par["legs"])
        if pid in existing:
            continue
        legs = [_leg(l) for l in par["legs"]]
        rows.append(dict(id=pid, created=now.isoformat(), type="parlay",
                         game_ids="|".join(l["game_id"] for l in par["legs"]),
                         desc=" + ".join(f"{l['label']}" for l in par["legs"]),
                         legs_json=json.dumps(legs, ensure_ascii=False),
                         odds=f"{par['odds']:.2f}", p=f"{par['p']:.4f}", ev=f"{par['ev']:.4f}",
                         stake=stake, result="", pnl="", title=f"פרליי {len(legs)} משחקים",
                         hint="", tier="", first_start=min(l["start"] for l in legs)))
    save(rows)


def _grade_prop(leg, box):
    """Player points. Did not play -> void (P): assumption, Winner's exact rule not verified.
    Whole-number line: landing exactly on it loses both over and under (Winner has an 'exactly' outcome)."""
    row = next((p for p in box if str(p["athlete_id"]) == str(leg.get("athlete_id"))), None)
    if row is None or row["dnp"]:
        return "P"
    pts, line = row["pts"], float(leg["line"])
    if pts == line:
        return "L"
    return "W" if (pts > line) == (leg["side"] == "over") else "L"


def _grade_leg(leg, g):
    hq, aq = g["hq"], g["aq"]
    if leg["period"] == "FG":
        h, a = g["hs"], g["as"]
    elif leg["period"] == "H1":
        h, a = sum(hq[:2]), sum(aq[:2])
    else:
        h, a = hq[0], aq[0]
    if leg["kind"] in ("spread", "ml"):
        m = (h - a) if leg["side"] == "home" else (a - h)
        v = m + float(leg["line"])
    elif leg["kind"] == "total":
        v = (h + a - float(leg["line"])) * (1 if leg["side"] == "over" else -1)
    else:  # team total
        pts = h if leg["team"] == g["home"] else a
        v = (pts - float(leg["line"])) * (1 if leg["side"] == "over" else -1)
    return "W" if v > 0 else "L" if v < 0 else "P"


def settle():
    rows = load()
    cache = {}
    changed = 0
    for r in rows:
        if r["result"]:
            continue
        legs = json.loads(r["legs_json"])
        res = []
        for leg in legs:
            gid = leg["game_id"]
            if gid not in cache:
                from datetime import datetime
                st = datetime.fromisoformat(leg["start"])
                for d in {(st - timedelta(hours=8)).date(), (st - timedelta(hours=8)).date() + timedelta(days=1)}:
                    for e in espn.scoreboard(d, use_cache=False).get("events", []):
                        gg = espn.parse_event(e)
                        if gg and gg["completed"]:
                            cache[gg["id"]] = gg
            g = cache.get(gid)
            if not g:
                res = None
                break
            if leg["kind"] == "player_points":
                box = espn.boxscore(gid)
                if not box:
                    res = None
                    break
                res.append(_grade_prop(leg, box))
                continue
            res.append(_grade_leg(leg, g))
        if not res:
            continue
        stake, odds = float(r["stake"] or 0), float(r["odds"])
        if "L" in res:
            r["result"], r["pnl"] = "L", f"{-stake:.2f}"
        else:
            eff = odds
            if "P" in res:  # push legs drop out at odds 1.0
                eff = 1.0
                for leg, x in zip(legs, res):
                    if x == "W":
                        eff *= float(leg["odds"])
            r["result"] = "W" if eff > 1 else "P"
            r["pnl"] = f"{stake * (eff - 1):.2f}"
        changed += 1
    save(rows)
    return changed, summary(rows)


def summary(rows=None):
    rows = rows if rows is not None else load()
    done = [r for r in rows if r["result"]]
    out = {}
    for t in ("single", "parlay"):
        d = [r for r in done if r["type"] == t]
        staked = sum(float(r["stake"] or 0) for r in d)
        pnl = sum(float(r["pnl"] or 0) for r in d)
        exp = sum(float(r["stake"] or 0) * float(r["ev"]) for r in d)
        out[t] = dict(n=len(d), wins=sum(r["result"] == "W" for r in d), staked=staked, pnl=pnl,
                      roi=pnl / staked if staked else 0.0, expected_pnl=exp)
    out["open"] = sum(1 for r in rows if not r["result"])
    return out
