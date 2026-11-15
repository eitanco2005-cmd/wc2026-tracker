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

    singles = sorted([b for b in all_bets if b["qualifies"]], key=lambda b: -b["ev"])
    # one single per market (never both sides)
    seen, s2 = set(), []
    for b in singles:
        if b["winner_mid"] not in seen:
            seen.add(b["winner_mid"]); s2.append(b)
    singles = [(b, engine.stake_for(b["kelly"], config.MAX_SINGLE_STAKE_PCT)) for b in s2]
    pars = parlays.build(all_bets, allow_negative=args.show_negative)
    pars = [(p, engine.stake_for(p["kelly"], config.MAX_PARLAY_STAKE_PCT) if p["ev"] > 0 else 0.0)
            for p in pars]

    if not args.no_log:
        tracker.log(now, singles, [p for p in pars if p[0]["ev"] > 0])
    html = report.render(now, rows, singles, pars, all_bets, model, tracker.summary(), warnings)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORTS_DIR / f"{now.astimezone(ZoneInfo(config.TZ)):%Y-%m-%d_%H%M}.html"
    out.write_text(html, encoding="utf-8")
    (config.REPORTS_DIR / "latest.html").write_text(html, encoding="utf-8")
    (config.ROOT / "index.html").write_text(html, encoding="utf-8")
    md = report.markdown(now, singles, pars, all_bets, tracker.summary())
    (config.REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")

    log("\n================ SUMMARY ================")
    log(f"{len(all_bets)} options checked in {len(rows)} games")
    if singles:
        for b, st in singles:
            log(f"  BET {b['away']}@{b['home']} | {b['label']} | {b['market']} | {b['odds']:.2f} | "
                f"p={b['p']:.1%} EV={b['ev']:+.1%} [{b['tier']}] | {st:.0f}₪")
    else:
        log("  No single bet with positive value today.")
    for p, st in pars:
        log(f"  PARLAY {len(p['legs'])} legs @ {p['odds']:.2f} p={p['p']:.1%} EV={p['ev']:+.1%} {st:.0f}₪: "
            + " + ".join(l["label"] for l in p["legs"]))
    log(f"\nReport: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


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
    html = report.render_sheet(now, rows, model)
    md = report.markdown_sheet(now, rows)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORTS_DIR / f"{now.astimezone(ZoneInfo(config.TZ)):%Y-%m-%d_%H%M}_sheet.html"
    out.write_text(html, encoding="utf-8")
    (config.REPORTS_DIR / "latest.html").write_text(html, encoding="utf-8")
    (config.ROOT / "index.html").write_text(html, encoding="utf-8")
    (config.REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    log(md)
    log(f"\nReport: {out}")


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
    ap.add_argument("cmd", nargs="?", default="today", choices=["today", "settle", "ratings"])
    ap.add_argument("--winner-file")
    ap.add_argument("--show-browser", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--show-negative", action="store_true")
    a = ap.parse_args()
    {"today": cmd_today, "settle": cmd_settle, "ratings": cmd_ratings}[a.cmd](a)


if __name__ == "__main__":
    main()
