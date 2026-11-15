"""Hebrew RTL HTML report."""
import html
from zoneinfo import ZoneInfo

from . import config
from .engine import team_name

TZ = ZoneInfo(config.TZ)
TIER_HE = {"A": "A · מעוגן בשוק", "B": "B · נגזר", "C": "C · רועש"}


def _pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def _ev_cls(e):
    return "pos" if e > 0 else "neg" if e < 0 else ""


def _t(dt):
    return dt.astimezone(TZ).strftime("%d/%m %H:%M")


def _anom(b):
    if not b.get("anomaly"):
        return ""
    return f"<span class='badge' title='{html.escape(b['anomaly'])}'>קו חריג</span>"


def render(now, games, singles, parlays, all_bets, model, track, warnings):
    e = html.escape
    avg_vig = sum(b["vig"] for b in all_bets) / len(all_bets) / 2 if all_bets else 0
    parts = [f"""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NBA × ווינר — {now.astimezone(TZ):%d/%m/%Y}</title>
<style>
:root{{--bg:#0f1115;--card:#171a21;--line:#272b35;--tx:#e8eaf0;--mut:#9aa1b2;--pos:#2fbf71;--neg:#e5534b;--acc:#f5a524}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Arial}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:18px;margin:32px 0 10px}}
.mut{{color:var(--mut)}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}}
th{{color:var(--mut);font-weight:500}}.pos{{color:var(--pos);font-weight:600}}.neg{{color:var(--neg)}}
.pill{{display:inline-block;padding:1px 8px;border-radius:99px;background:#232836;font-size:12px;color:var(--mut)}}
.warn{{border-color:#5a4313;background:#1f1a10}}.big{{font-size:20px;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
details summary{{cursor:pointer;color:var(--mut)}} .warn-line{{color:var(--acc);font-size:13px;margin-top:4px}}
.badge{{display:inline-block;margin-inline-start:6px;padding:0 6px;border-radius:6px;background:#3a2c0c;color:var(--acc);font-size:11px;cursor:help}} .num{{direction:ltr;unicode-bidi:embed}}
</style></head><body><main>
<h1>NBA × ווינר — המלצות</h1>
<div class="mut">נוצר {now.astimezone(TZ):%d/%m/%Y %H:%M} · {len(games)} משחקים · {len(all_bets)} אפשרויות נבדקו</div>"""]

    parts.append(f"""<div class="card warn"><b>לפני הכול:</b> המרווח של ווינר בשווקי NBA דו-כיווניים הוא בממוצע
<b class="num">{_pct(avg_vig * 2)}</b> לשוק (יחס 1.75/1.75 ⇐ צריך לנצח 57.1% רק כדי לא להפסיד). בפרליי המרווח מצטבר בכל רגל.
המערכת ממליצה רק כשההסתברות המשוקללת מכסה את המרווח — ולכן בהרבה ימים התשובה הנכונה היא "אין הימור".</div>""")
    for w in warnings:
        parts.append(f'<div class="card warn">{e(w)}</div>')

    # ---- track record
    s, p = track["single"], track["parlay"]
    parts.append(f"""<h2>מעקב ביצועים</h2><div class="grid">
<div class="card"><div class="mut">בודדים שהוכרעו</div><div class="big">{s['n']}</div><div class="mut">{s['wins']} זכיות</div></div>
<div class="card"><div class="mut">רווח/הפסד בודדים</div><div class="big {_ev_cls(s['pnl'])} num">{s['pnl']:+.0f} ₪</div><div class="mut">ROI <span class="num">{_pct(s['roi'])}</span> · צפוי <span class="num">{s['expected_pnl']:+.0f}</span></div></div>
<div class="card"><div class="mut">רווח/הפסד פרליים</div><div class="big {_ev_cls(p['pnl'])} num">{p['pnl']:+.0f} ₪</div><div class="mut">{p['n']} הוכרעו · ROI <span class="num">{_pct(p['roi'])}</span></div></div>
<div class="card"><div class="mut">פתוחים</div><div class="big">{track['open']}</div><div class="mut">הרץ <code>settle</code> מחר</div></div></div>""")

    n_anom = sum(1 for b, _ in singles if b.get("anomaly"))
    if n_anom:
        parts.append(f"""<div class="card warn"><b>⚠ {n_anom} מתוך {len(singles)} ההמלצות</b> מבוססות על קווי מחצית/רבע של ווינר
שלא מתאימים לקו המשחק המלא שלהם (מסומנות "קו חריג"). זו יכולה להיות טעות תמחור של ווינר — או מידע שאין למודל.
בפרליים, רגליים כאלה תלויות זו בזו.</div>""")

    # ---- singles
    parts.append("<h2>הימורים בודדים מומלצים</h2>")
    if not singles:
        parts.append('<div class="card">אין היום הימור בודד שעובר את הסף. זו לא תקלה — זה המצב הרגיל מול מרווח של ווינר.</div>')
    else:
        parts.append("<div class='card'><table><tr><th>משחק</th><th>שוק</th><th>בחירה</th><th>יחס</th><th>הסתברות</th><th>EV</th><th>דרגה</th><th>סכום</th></tr>")
        for b, stake in singles:
            parts.append(f"<tr><td>{e(team_name(b['away']))} @ {e(team_name(b['home']))}<div class='mut'>{_t(b['start'])}</div></td>"
                         f"<td>{e(b['market'])}</td><td><b>{e(b['label'])}</b>{_anom(b)}</td><td class='num'>{b['odds']:.2f}</td>"
                         f"<td class='num'>{_pct(b['p'])}</td><td class='pos num'>{_pct(b['ev'])}</td>"
                         f"<td><span class='pill'>{TIER_HE[b['tier']]}</span></td><td class='num'>{stake:.0f} ₪</td></tr>")
        parts.append("</table></div>")

    # ---- parlays
    parts.append("<h2>פרליים</h2>")
    if not parlays:
        parts.append('<div class="card">אין פרליי עם תוחלת חיובית היום. פרליי מרגליים עם EV שלילי רק מכפיל את ההפסד הצפוי.</div>')
    for par, stake in parlays:
        n_anom = sum(1 for l in par["legs"] if l.get("anomaly"))
        corr = ("<div class='neg'>⚠ " + str(n_anom) + " מהרגליים נשענות על קו חריג של ווינר מאותו סוג — "
                "אם ההנחה שגויה הן נוטות להפסיד ביחד, והסיכוי האמיתי נמוך מהמוצג.</div>") if n_anom >= 2 else ""
        legs = "".join(f"<li>{e(team_name(l['away']))} @ {e(team_name(l['home']))} — <b>{e(l['label'])}</b>{_anom(l)} "
                       f"<span class='mut'>({e(l['market'])}, <span class='num'>{l['odds']:.2f}</span>, {_pct(l['p'])})</span></li>"
                       for l in par["legs"])
        parts.append(f"<div class='card'><div><b>{len(par['legs'])} רגליים</b> · יחס <b class='num'>{par['odds']:.2f}</b> · "
                     f"סיכוי <span class='num'>{_pct(par['p'])}</span> · EV <span class='pos num'>{_pct(par['ev'])}</span> · "
                     f"סכום <span class='num'>{stake:.0f} ₪</span></div>{corr}<ul>{legs}</ul></div>")

    # ---- per game research
    parts.append("<h2>מחקר לפי משחק</h2>")
    for g, proj, inj in games:
        mk = (f"<span class='num'>{proj['market_margin']:+.1f}</span> / <span class='num'>{proj['market_total']:.1f}</span>"
              if proj["market_margin"] is not None and proj["market_total"] is not None else "—")
        o = g.get("odds") or {}
        move = ""
        if o.get("spread_open_home_line") == o.get("spread_open_home_line") and o.get("spread_home_line") is not None \
                and o.get("spread_open_home_line") is not None and o["spread_open_home_line"] != o["spread_home_line"]:
            move = f" · תזוזת קו: <span class='num'>{o['spread_open_home_line']:+.1f} → {o['spread_home_line']:+.1f}</span>"
        injs = []
        for side in ("home", "away"):
            tot, det = inj[side]
            if det:
                injs.append(f"<b>{e(team_name(g[side]))}</b> (−{tot:.1f}): " + ", ".join(
                    f"{e(d['name'])} [{e(d['status'])}, {d['impact']}]" for d in det))
        b2b = [team_name(g[s]) for s in ("home", "away") if proj[f"b2b_{s}"]]
        parts.append(f"""<div class="card"><b>{e(team_name(g['away']))} @ {e(team_name(g['home']))}</b> <span class="mut">{_t(g['start'])}</span>
<table><tr><th></th><th>הפרש בית צפוי</th><th>סך נקודות</th></tr>
<tr><td>מודל (דירוגים+מנוחה+פציעות)</td><td class="num">{proj['model_margin']:+.1f}</td><td class="num">{proj['model_total']:.1f}</td></tr>
<tr><td>שוק חד (DraftKings, ללא מרווח)</td><td colspan="2">{mk}{move}</td></tr>
<tr><td><b>משוקלל</b></td><td class="num"><b>{proj['margin']:+.1f}</b></td><td class="num"><b>{proj['total']:.1f}</b></td></tr></table>
<div class="mut">דירוג: {e(g['home'])} <span class="num">{model.rating(g['home']):+.1f}</span> · {e(g['away'])} <span class="num">{model.rating(g['away']):+.1f}</span>
{(' · בק-טו-בק: ' + e(', '.join(b2b))) if b2b else ''}</div>
{('<div class="mut">פציעות: ' + ' | '.join(injs) + '</div>') if injs else ''}
{''.join('<div class="warn-line">⚠ ' + e(a) + '</div>' for a in proj.get('anomalies', []))}
{('<div class="neg">⚠ פער גדול בין המודל לשוק — כנראה מידע שהמודל לא יודע (פציעה/מנוחה). ההימורים במשחק הזה נחסמו.</div>') if proj.get('gap_margin') or proj.get('gap_total') else ''}</div>""")

    # ---- all options
    parts.append("<h2>כל האפשרויות שנבדקו</h2><details><summary>הצג ({})</summary><div class='card'><table>"
                 "<tr><th>משחק</th><th>שוק</th><th>בחירה</th><th>יחס</th><th>הסתברות</th><th>EV</th><th>דרגה</th></tr>".format(len(all_bets)))
    for b in sorted(all_bets, key=lambda x: -x["ev"]):
        parts.append(f"<tr><td>{e(b['away'])}@{e(b['home'])}</td><td>{e(b['market'])}</td><td>{e(b['label'])}</td>"
                     f"<td class='num'>{b['odds']:.2f}</td><td class='num'>{_pct(b['p'])}</td>"
                     f"<td class='{_ev_cls(b['ev'])} num'>{_pct(b['ev'])}</td><td>{b['tier']}</td></tr>")
    parts.append("</table></div></details>")

    # ---- method
    sd, fr = model.sd, model.frac
    parts.append(f"""<h2>שיטה</h2><div class="card mut">
<p>1. <b>מודל</b>: דירוגי קבוצות ב-ridge regression על כל משחקי העונה (משקל דועך, חצי-חיים {config.HALF_LIFE_DAYS} יום) + העונה הקודמת כ-prior (משקל {config.PRIOR_SEASON_WEIGHT}).
יתרון ביתיות נלמד: <span class="num">{model.hca:+.2f}</span> נק'. השפעת בק-טו-בק נלמדה: <span class="num">{model.b2b_coef:+.2f}</span> נק'. מודל התקפה/הגנה נפרד לסך נקודות.</p>
<p>2. <b>פציעות</b>: סטטוס מ-ESPN × ערך השחקן מעל מחליף (נקודות, אסיסטים, ריבאונדים, חטיפות/חסימות, איבודים, דקות). שחקנים שכבר נעדרו רוב העונה לא נספרים פעמיים.</p>
<p>3. <b>שוק חד</b>: קווי DraftKings הופכים להסתברות ללא מרווח ומשוקללים {int(config.MARKET_WEIGHT * 100)}% מול {int((1 - config.MARKET_WEIGHT) * 100)}% מודל.</p>
<p>4. <b>התפלגויות כוילו מהיסטוריה</b>: סטיית תקן הפרש <span class="num">{sd['FG_margin']:.1f}</span>, סך <span class="num">{sd['FG_total']:.1f}</span>, קבוצתי <span class="num">{sd['team_pts']:.1f}</span>;
מחצית: <span class="num">{fr['H1_margin']:.2f}</span>×הפרש (σ <span class="num">{sd['H1_margin']:.1f}</span>), <span class="num">{fr['H1_total']:.3f}</span>×סך; רבע: <span class="num">{fr['Q1_margin']:.2f}</span>×הפרש (σ <span class="num">{sd['Q1_margin']:.1f}</span>), <span class="num">{fr['Q1_total']:.3f}</span>×סך.</p>
<p>5. <b>EV</b> = הסתברות × יחס ווינר − 1. סף: A ≥ {_pct(config.MIN_EV['A'], 0)}, B ≥ {_pct(config.MIN_EV['B'], 0)}, C ≥ {_pct(config.MIN_EV['C'], 0)}. סכום: רבע-קלי, תקרה {_pct(config.MAX_SINGLE_STAKE_PCT, 0)} מהבנקרול.</p>
<p>6. <b>פרליים</b>: רק מרגליים עם EV חיובי, רגל אחת למשחק (ללא תלות), סיכוי מינימלי {_pct(config.PARLAY_MIN_PROB, 0)}.</p>
<p>לא נתמכים (אין מודל אמין): שלשות, סל ראשון, הראשונה ל-10/20, מחצית/סיום, כוכב הלילה.</p></div>
<p class="mut">הימורים כרוכים בסיכון להפסד כספי. קבע מראש בנקרול שאתה מוכן להפסיד כולו, ואל תרדוף אחרי הפסדים.</p>
</main></body></html>""")
    return "\n".join(parts)


def markdown(now, singles, parlays, all_bets, track):
    """Short summary for the GitHub Actions run page."""
    L = [f"# NBA × Winner — {now.astimezone(TZ):%d/%m/%Y %H:%M}",
         f"{len(all_bets)} options checked.", ""]
    if singles:
        L += ["## Bets", "| Game | Market | Pick | Odds | P | EV | Stake |", "|---|---|---|---|---|---|---|"]
        for b, st in singles:
            L.append(f"| {b['away']}@{b['home']} {_t(b['start'])} | {b['market']} | **{b['label']}** | "
                     f"{b['odds']:.2f} | {_pct(b['p'])} | {_pct(b['ev'])} [{b['tier']}] | {st:.0f}₪ |")
    else:
        L.append("**No single bet with positive value today.**")
    L.append("")
    if parlays:
        L.append("## Parlays")
        for p, st in parlays:
            L.append(f"- **{len(p['legs'])} legs @ {p['odds']:.2f}** · P {_pct(p['p'])} · EV {_pct(p['ev'])} · {st:.0f}₪: "
                     + " + ".join(f"{l['away']}@{l['home']} {l['label']}" for l in p["legs"]))
    s = track["single"]
    L += ["", f"Track record (singles): {s['n']} graded, P&L {s['pnl']:+.0f}₪, ROI {_pct(s['roi'])}, "
              f"expected {s['expected_pnl']:+.0f}₪"]
    return "\n".join(L)


def _head(title):
    return f"""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
:root{{--bg:#0f1115;--card:#171a21;--line:#272b35;--tx:#e8eaf0;--mut:#9aa1b2;--pos:#2fbf71;--neg:#e5534b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Arial}}
main{{max-width:900px;margin:0 auto;padding:20px 14px 60px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:26px 0 8px}}
.mut{{color:var(--mut)}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:10px 0}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:6px 7px;border-bottom:1px solid var(--line);text-align:right}}
th{{color:var(--mut);font-weight:500}}.pos{{color:var(--pos);font-weight:700}}.neg{{color:var(--neg)}}.warn{{border-color:#5a4313;background:#1f1a10}}
.num{{direction:ltr;unicode-bidi:embed}}
</style></head><body><main>"""


_PER = {"FG": "משחק מלא", "H1": "מחצית ראשונה", "Q1": "רבע ראשון"}


def _odds_cell(x):
    need, p = x
    cls = "pos" if need <= 1.85 else "mut" if need <= 2.0 else "neg"
    return f"<td class='{cls} num'>{need:.2f}</td>"


def render_sheet(now, rows, model):
    e = html.escape
    P = [_head(f"NBA דף מחירים — {now.astimezone(TZ):%d/%m}"),
         f"<h1>NBA — דף מחירים להיום</h1><div class='mut'>נוצר {now.astimezone(TZ):%d/%m/%Y %H:%M} · {len(rows)} משחקים</div>",
         """<div class="card warn"><b>איך משתמשים:</b> פתח את המשחק בווינר, מצא את הקו שהם מציעים בטבלה המתאימה,
והשווה: אם היחס בווינר <b>גבוה או שווה</b> למספר בטבלה — יש ערך. אם נמוך — לא להמר.
<span class="pos">ירוק</span> = ווינר נוטה להציע כזה יחס (≤1.85) ⇐ שווה לבדוק. אפור/אדום = כמעט אף פעם לא.</div>"""]
    for g, proj, inj, sheet in rows:
        H, A = ABBR_TO_HE_(g["home"]), ABBR_TO_HE_(g["away"])
        injs = []
        for side in ("home", "away"):
            tot, det = inj[side]
            if det:
                injs.append(f"<b>{e(ABBR_TO_HE_(g[side]))}</b> (−{tot:.1f}): " + ", ".join(
                    f"{e(d['name'])} [{e(d['status'])}]" for d in det))
        mm = '—' if proj['market_margin'] is None else f"{proj['market_margin']:+.1f}"
        mt = '—' if proj['market_total'] is None else f"{proj['market_total']:.1f}"
        P.append(f"""<h2>{e(A)} @ {e(H)} <span class="mut">{_t(g['start'])}</span></h2><div class="card">
<div class="mut">צפי משוקלל: {e(H)} <span class="num">{proj['margin']:+.1f}</span> · סך <span class="num">{proj['total']:.1f}</span>
&nbsp;|&nbsp; מודל <span class="num">{proj['model_margin']:+.1f} / {proj['model_total']:.1f}</span>
&nbsp;|&nbsp; שוק <span class="num">{mm} / {mt}</span></div>
{('<div class="mut">פציעות: ' + ' | '.join(injs) + '</div>') if injs else ''}""")
        for per in ("FG", "H1", "Q1"):
            sp, to = sheet.get((per, "spread"), {}), sheet.get((per, "total"), {})
            P.append(f"<div style='margin-top:10px'><b>{_PER[per]}</b></div><div style='display:flex;gap:14px;flex-wrap:wrap'>")
            P.append(f"<table style='flex:1;min-width:260px'><tr><th>יתרון {e(H)}</th><th>{e(H)}</th><th>{e(A)}</th></tr>")
            for L in sorted(sp):
                row = sp[L]
                if row["blocked"]:
                    P.append(f"<tr><td class='num'>{L:+g}</td><td colspan=2 class='neg'>חסום</td></tr>"); continue
                P.append(f"<tr><td class='num'>{L:+g}</td>{_odds_cell(row['home'])}{_odds_cell(row['away'])}</tr>")
            P.append("</table><table style='flex:1;min-width:220px'><tr><th>קו</th><th>מעל</th><th>מתחת</th></tr>")
            for L in sorted(to):
                row = to[L]
                if row["blocked"]:
                    P.append(f"<tr><td class='num'>{L:g}</td><td colspan=2 class='neg'>חסום</td></tr>"); continue
                P.append(f"<tr><td class='num'>{L:g}</td>{_odds_cell(row['over'])}{_odds_cell(row['under'])}</tr>")
            P.append("</table></div>")
        P.append("</div>")
    sd = model.sd
    P.append(f"""<p class="mut">מודל: דירוגי קבוצות (עונה נוכחית + קודמת), ביתיות <span class="num">{model.hca:+.2f}</span>,
בק-טו-בק <span class="num">{model.b2b_coef:+.2f}</span>, פציעות, ושוק DraftKings ללא מרווח ({int(config.MARKET_WEIGHT*100)}%).
σ הפרש <span class="num">{sd['FG_margin']:.1f}</span>, σ סך <span class="num">{sd['FG_total']:.1f}</span>.
המספר בטבלה כבר כולל את סף ה-EV: משחק מלא {_pct(config.MIN_EV['A'],0)}, מחצית {_pct(config.MIN_EV['B'],0)}, רבע {_pct(config.MIN_EV['C'],0)}.</p></main></body></html>""")
    return "\n".join(P)


def markdown_sheet(now, rows):
    L = [f"# NBA price sheet — {now.astimezone(TZ):%d/%m/%Y %H:%M}",
         "Find Winner's line below; bet only if Winner's odds are **≥** the number. Full tables (halves/quarters) in reports/latest.html.", ""]
    for g, proj, inj, sheet in rows:
        L.append(f"### {g['away']} @ {g['home']} — {_t(g['start'])}  (proj {g['home']} {proj['margin']:+.1f}, total {proj['total']:.1f})")
        sp, to = sheet.get(("FG", "spread"), {}), sheet.get(("FG", "total"), {})
        L.append(f"| {g['home']} line | {g['home']} | {g['away']} | | Total | Over | Under |")
        L.append("|---|---|---|---|---|---|---|")
        for a, b in zip(sorted(sp), sorted(to)):
            ra, rb = sp[a], to[b]
            fa = "blocked | blocked" if ra["blocked"] else f"{ra['home'][0]:.2f} | {ra['away'][0]:.2f}"
            fb = "blocked | blocked" if rb["blocked"] else f"{rb['over'][0]:.2f} | {rb['under'][0]:.2f}"
            L.append(f"| {a:+g} | {fa} | | {b:g} | {fb} |")
        L.append("")
    return "\n".join(L)


def ABBR_TO_HE_(a):
    from .teams import ABBR_TO_HE
    return ABBR_TO_HE.get(a, a)
