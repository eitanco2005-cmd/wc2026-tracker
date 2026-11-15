"""NBA × Winner daily value finder.

Usage:
  python run.py                 # today's recommendations -> reports/YYYY-MM-DD.html
  python run.py settle          # grade past picks against final scores
  python run.py ratings         # print current team ratings
Options:
  --winner-file PATH            # use a saved Winner JSON instead of fetching
  --show-browser                # visible browser for the Winner fetch (if blocked)
  --no-open                     # don't open the report
  --no-log                      # don't record picks in data/picks.csv
  --show-negative               # also build "least-bad" parlays (for curiosity)
"""
import argparse
import sys
import webbrowser
from datetime import timedelta
from zoneinfo import ZoneInfo

from nbaw import config, espn, engine, parlays, report, tracker, winner
from nbaw.model import Model, team_injury_impact
from nbaw.teams import ABBR_TO_NAME


def log(msg):
    print(msg, flush=True)


def build_model(now):
    log("[1] Loading ESPN results history (first run 2-4 min, then cached)...")
    hist = espn.history(now.date(), progress=log)
    log(f"    {len(hist)} games ({sum(g['current'] for g in hist)} this season)")
    return Model(hist, now)


def cmd_today(args):
    now = espn.now_utc()
    warnings = []
    log("[0] Fetching Winner NBA line...")
    try:
        raw = winner.fetch_line(args.winner_file, args.show_browser)
    except Exception as e:  # noqa: BLE001
        log(f"    Winner unavailable ({str(e).splitlines()[0]}) -> price-sheet mode")
        return cmd_sheet(now)
    wm = winner.parse(raw)
    log(f"    {len(raw)} NBA markets on Winner, {len(wm)} supported")
    if not wm:
        log("No NBA game markets on Winner right now.")
        return

    model = build_model(now)

    log("[2] Games, market lines, injuries...")
    games = [g for g in espn.todays_games(now) if g["start"] > now + timedelta(minutes=5)]
    matched = engine.match_games(wm, games)
    unmatched = {(m["home"], m["away"]) for m in wm} - {
        (g["home"], g["away"]) for g, _ in matched.values()} - {
        (g["away"], g["home"]) for g, _ in matched.values()}
    if unmatched:
        warnings.append("משחקים בווינר שלא הותאמו ל-ESPN: " + ", ".join(f"{a}-{b}" for a, b in unmatched))
    inj = espn.injuries()
    name_inj = {k: v for k, v in inj.items()}

    rows, all_bets = [], []
    for gid, (g, mkts) in sorted(matched.items(), key=lambda kv: kv[1][0]["start"]):
        if not g.get("odds"):
            warnings.append(f"אין קו שוק ל-{g['away']}@{g['home']} — מבוסס מודל בלבד (דרגה מורדת).")
        ih = team_injury_impact(name_inj.get(ABBR_TO_NAME.get(g["home"]), []),
                                model.cur_gp[g["home"]], espn.athlete_stats)
        ia = team_injury_impact(name_inj.get(ABBR_TO_NAME.get(g["away"]), []),
                                model.cur_gp[g["away"]], espn.athlete_stats)
        proj, bets = engine.evaluate_game(g, mkts, model, ih[0], ia[0])
        rows.append((g, proj, {"home": ih, "away": ia}))
        all_bets += bets

    publish(now, rows, all_bets, model, warnings, args)


def choose_tickets(all_bets, args):
    """Best singles (one per game) + best rule-valid parlay."""
    from nbaw import rules
    cands = sorted([b for b in all_bets if b["qualifies"] and rules.single_ok(b)], key=lambda b: -b["ev"])
    singles, games = [], set()
    for b in cands:
        if b["game_id"] in games:
            continue
        games.add(b["game_id"]); singles.append(b)
        if len(singles) >= config.MAX_SINGLES_PER_DAY:
            break
    pars = [p for p in parlays.build(all_bets, allow_negative=args.show_negative)
            if p["ev"] > 0 and not rules.parlay_problems(p["legs"])][: config.MAX_PARLAYS_PER_DAY]
    return singles, pars


def publish(now, rows, all_bets, model, warnings, args):
    from nbaw import project
    st = project.state(tracker.load())
    singles, pars = choose_tickets(all_bets, args) if st["status"] == "active" else ([], [])
    singles, pars = project.size_day(st["balance"], singles, pars)
    if not args.no_log:
        tracker.log(now, singles, pars)
    write_meta(picks_at=now.isoformat())
    full = report.render(now, rows, singles, pars, all_bets, model, tracker.summary(), warnings)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{now.astimezone(ZoneInfo(config.TZ)):%Y-%m-%d_%H%M}"
    (config.REPORTS_DIR / f"{stamp}.html").write_text(full, encoding="utf-8")
    (config.REPORTS_DIR / "latest_full.html").write_text(full, encoding="utf-8")
    render_site(now)

    log("\n================ SUMMARY ================")
    log(f"{len(all_bets)} options checked in {len(rows)} games | balance {st['balance']:.0f} ({st['status']})")
    for b, stk in singles:
        log(f"  SINGLE {b['away']}@{b['home']} | {b['label']} | {b['market']} | {b['odds']:.2f} | "
            f"p={b['p']:.1%} EV={b['ev']:+.1%} [{b['tier']}] | {stk} ILS")
    for p, stk in pars:
        log(f"  PARLAY {len(p['legs'])} legs @ {p['odds']:.2f} p={p['p']:.1%} EV={p['ev']:+.1%} {stk} ILS: "
            + " + ".join(f"{l['away']}@{l['home']} {l['label']}" for l in p["legs"]))
    if not singles and not pars:
        log("  No bets today.")


def write_meta(**kw):
    import json
    p = config.DATA_DIR / "meta.json"
    m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    m.update(kw)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def render_site(now):
    import json
    from nbaw import project, site
    rows = tracker.load()
    mp = config.DATA_DIR / "meta.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    html = site.render(now, project.state(rows), rows, meta)
    (config.ROOT / "index.html").write_text(html, encoding="utf-8")
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_DIR / "latest.html").write_text(html, encoding="utf-8")


def cmd_sheet(now):
    """No Winner odds: minimum odds needed per line, to compare in the Winner app."""
    model = build_model(now)
    log("[2] Games, market lines, injuries...")
    games = [g for g in espn.todays_games(now) if g["start"] > now + timedelta(minutes=5)
             and g["start"] < now + timedelta(hours=20)]
    inj = espn.injuries()
    rows = []
    for g in sorted(games, key=lambda x: x["start"]):
        ih = team_injury_impact(inj.get(ABBR_TO_NAME.get(g["home"]), []), model.cur_gp[g["home"]], espn.athlete_stats)
        ia = team_injury_impact(inj.get(ABBR_TO_NAME.get(g["away"]), []), model.cur_gp[g["away"]], espn.athlete_stats)
        proj, sheet = engine.price_sheet(g, model, ih[0], ia[0])
        rows.append((g, proj, {"home": ih, "away": ia}, sheet))
    save_snapshot(now, model, rows)
    html = report.render_sheet(now, rows, model)
    md = report.markdown_sheet(now, rows)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORTS_DIR / f"{now.astimezone(ZoneInfo(config.TZ)):%Y-%m-%d_%H%M}_sheet.html"
    out.write_text(html, encoding="utf-8")
    (config.REPORTS_DIR / "latest_full.html").write_text(html, encoding="utf-8")
    (config.REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    render_site(now)
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    log(md)
    log(f"\nReport: {out}")


def save_snapshot(now, model, rows):
    """Projections for later use with Winner odds captured elsewhere (Claude in Chrome)."""
    import json
    snap = dict(created=now.isoformat(), sd=model.sd, frac=model.frac, hca=model.hca,
                b2b=model.b2b_coef, ratings={t: model.rating(t) for t in model.teams},
                games=[dict(game={k: (v.isoformat() if k == "start" else v) for k, v in g.items()
                                  if k in ("id", "start", "home", "away", "odds", "neutral")},
                            proj=proj, inj={"home": inj["home"], "away": inj["away"]})
                       for g, proj, inj, *_ in rows])
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "projections.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                                      encoding="utf-8")


class SnapModel:
    def __init__(self, snap):
        self.sd, self.frac, self.hca, self.b2b_coef = snap["sd"], snap["frac"], snap["hca"], snap["b2b"]
        self._r = snap["ratings"]

    def rating(self, t):
        return self._r.get(t, 0.0)


def cmd_picks(args):
    """Winner odds (captured via Claude in Chrome) + saved projections -> picks & parlays."""
    import json
    from datetime import datetime
    now = espn.now_utc()
    snap = json.loads((config.DATA_DIR / "projections.json").read_text(encoding="utf-8"))
    model = SnapModel(snap)
    log(f"Projections from {snap['created']}")
    raw = json.loads(open(args.winner_file, encoding="utf-8").read())
    raw = raw["markets"] if isinstance(raw, dict) else raw
    wm = winner.parse(raw)
    games = []
    for x in snap["games"]:
        g = dict(x["game"]); g["start"] = datetime.fromisoformat(g["start"])
        if g["start"] > now + timedelta(minutes=5):
            games.append((g, x["proj"], x["inj"]))
    matched = engine.match_games(wm, [g for g, _, _ in games])
    by_id = {g["id"]: (proj, inj) for g, proj, inj in games}
    rows, all_bets, warnings = [], [], []
    for gid, (g, mkts) in sorted(matched.items(), key=lambda kv: kv[1][0]["start"]):
        proj, inj = by_id[gid]
        bets = engine.evaluate(g, mkts, proj, model.sd, model.frac)
        rows.append((g, proj, {k: tuple(v) for k, v in inj.items()}))
        all_bets += bets
    log(f"{len(wm)} Winner markets, {len(rows)} games matched")
    publish(now, rows, all_bets, model, warnings, args)


def cmd_settle(_):
    n, s = tracker.settle()
    log(f"הוכרעו {n} הימורים.")
    for t in ("single", "parlay"):
        x = s[t]
        log(f"{t}: {x['n']} | זכיות {x['wins']} | הושקע {x['staked']:.0f}₪ | רווח {x['pnl']:+.0f}₪ | "
            f"ROI {x['roi']:+.1%} | צפוי {x['expected_pnl']:+.0f}₪")
    log(f"פתוחים: {s['open']}")


def cmd_ratings(_):
    m = build_model(espn.now_utc())
    log(f"יתרון ביתיות {m.hca:+.2f} | בק-טו-בק {m.b2b_coef:+.2f}")
    for t, name, r, gp in m.ratings_table():
        log(f"{t:5} {name:28} {r:+6.1f}  ({gp} מש')")
    log(f"SD: { {k: round(v, 2) for k, v in m.sd.items()} }")
    log(f"FRAC: { {k: round(v, 3) for k, v in m.frac.items()} }")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="today", choices=["today", "settle", "ratings", "picks"])
    ap.add_argument("--winner-file")
    ap.add_argument("--show-browser", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--show-negative", action="store_true")
    a = ap.parse_args()
    {"today": cmd_today, "settle": cmd_settle, "ratings": cmd_ratings, "picks": cmd_picks}[a.cmd](a)


if __name__ == "__main__":
    main()
