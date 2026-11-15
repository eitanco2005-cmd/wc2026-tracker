"""Mobile-first Hebrew site, rendered from the ledger (data/picks.csv)."""
import html
import json
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .hebrew import CONF

TZ = ZoneInfo(config.TZ)
e = html.escape


def _ils(x, sign=False):
    x = float(x)
    s = f"{abs(x):,.0f} ₪"
    if sign:
        return ("+" if x > 0 else "−" if x < 0 else "") + s
    return ("−" if x < 0 else "") + s


def _when(iso):
    d = datetime.fromisoformat(iso).astimezone(TZ)
    return d.strftime("%H:%M"), d.strftime("%d/%m")


def _spark(history):
    pts = [v for _, v in history]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts + [config.START_BALANCE]), max(pts + [config.START_BALANCE])
    span = (hi - lo) or 1
    w, h = 300, 60
    xy = [(i * w / (len(pts) - 1), h - (v - lo) / span * h) for i, v in enumerate(pts)]
    base = h - (config.START_BALANCE - lo) / span * h
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(xy))
    color = "var(--win)" if pts[-1] >= config.START_BALANCE else "var(--loss)"
    return (f'<svg class="spark" viewBox="0 -4 {w} {h + 8}" preserveAspectRatio="none" aria-hidden="true">'
            f'<line x1="0" x2="{w}" y1="{base:.1f}" y2="{base:.1f}" class="base"/>'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>')


def _reason(leg, odds):
    if leg.get("anomaly"):
        return "ווינר קבע כאן קו שלא מתאים לקו שלו למשחק כולו. זה ההימור הכי \"זול\" שמצאנו — אבל גם זה שכדאי לבדוק."
    p = float(leg.get("p") or 0)
    return f"לפי המודל הסיכוי שזה יקרה {p:.0%}. ווינר משלם כאילו הסיכוי {1 / float(odds):.0%}."


def _leg_html(l, show_odds=True):
    t, d = _when(l["start"])
    conf = CONF.get(l.get("tier", ""), "")
    warn = '<div class="warn">⚠ קו חריג של ווינר — אם נראה לך מוזר, דלג.</div>' if l.get("anomaly") else ""
    odds = f'<span class="odds">{float(l["odds"]):.2f}</span>' if show_odds else ""
    return f"""<div class="leg">
  <div class="game">{e(l['game'])} · <span class="muted">{d} {t}</span></div>
  <div class="bet">{e(l['title'])} {odds}</div>
  <div class="hint">בווינר: {e(l['hint'])}</div>
  {f'<div class="conf">ביטחון: <b>{conf}</b></div>' if conf else ''}{warn}
</div>"""


def _ticket(r):
    legs = json.loads(r["legs_json"])
    stake, odds = float(r["stake"] or 0), float(r["odds"])
    win = stake * odds
    if r["type"] == "single":
        l = legs[0]
        body = _leg_html(l, show_odds=False)
        reason = _reason(l, odds)
        head = '<span class="tag single">הימור בודד</span>'
    else:
        body = "".join(_leg_html(l) for l in legs)
        n_anom = sum(1 for l in legs if l.get("anomaly"))
        reason = (f"כל {len(legs)} הבחירות צריכות להצליח. סיכוי משוער {float(r['p']):.0%}."
                  + (" שים לב: כמה רגליים נשענות על אותו סוג קו חריג — הן נוטות להצליח או להיכשל ביחד."
                     if n_anom >= 2 else ""))
        head = f'<span class="tag parlay">פרליי · {len(legs)} משחקים</span>'
    return f"""<article class="ticket">
  <div class="thead">{head}</div>
  {body}
  <div class="nums">
    <div><span>יחס</span><b>{odds:.2f}</b></div>
    <div><span>לשים</span><b>{_ils(stake)}</b></div>
    <div><span>אם נכון מקבלים</span><b class="win">{_ils(win)}</b></div>
  </div>
  <div class="reason">{e(reason)}</div>
</article>"""


def _history(rows):
    by_day = OrderedDict()
    for r in sorted(rows, key=lambda r: r.get("first_start") or r["created"], reverse=True):
        day = _when(r.get("first_start") or r["created"])[1]
        by_day.setdefault(day, []).append(r)
    out = []
    for day, rs in by_day.items():
        pnl = sum(float(r["pnl"] or 0) for r in rs)
        items = []
        for r in rs:
            icon = {"W": "✓", "L": "✗", "P": "↺"}.get(r["result"], "⏳")
            cls = {"W": "w", "L": "l", "P": "p"}.get(r["result"], "o")
            legs = json.loads(r["legs_json"])
            title = legs[0].get("title", r["desc"]) if r["type"] == "single" else \
                f"פרליי {len(legs)}: " + " + ".join(l.get("title", l.get("label", "")) for l in legs)
            res = _ils(r["pnl"], sign=True) if r["result"] else "ממתין"
            items.append(f'<li class="{cls}"><span class="ic">{icon}</span><span class="tt">{e(title)}</span>'
                         f'<span class="am">{_ils(r["stake"])} · {res}</span></li>')
        out.append(f'<div class="day"><div class="dh"><b>{day}</b><span class="{"win" if pnl > 0 else "loss" if pnl < 0 else "muted"}">'
                   f'{_ils(pnl, sign=True) if any(r["result"] for r in rs) else ""}</span></div><ul>{"".join(items)}</ul></div>')
    return "".join(out) or '<p class="muted">עוד אין הימורים שהוכרעו.</p>'


def render(now, st, rows, meta):
    pending = [r for r in rows if not r["result"]]
    settled = [r for r in rows if r["result"]]
    upcoming = [r for r in pending if datetime.fromisoformat(r.get("first_start") or r["created"]) > now]
    running = [r for r in pending if r not in upcoming]
    total_stake = sum(float(r["stake"] or 0) for r in upcoming)
    max_win = sum(float(r["stake"] or 0) * float(r["odds"]) for r in upcoming)
    picks_at = meta.get("picks_at")
    picks_today = picks_at and datetime.fromisoformat(picks_at).astimezone(TZ).date() == now.astimezone(TZ).date()

    # ---- status banner
    if st["status"] == "target":
        banner = '<div class="banner good">🎯 הגעת למטרה! הפרויקט הסתיים — לא מומלץ להמשיך להמר.</div>'
    elif st["status"] == "stopped":
        banner = (f'<div class="banner bad">⛔ היתרה ירדה מתחת לרצפה ({_ils(st["floor_bal"])}). '
                  'הפרויקט נעצר — אין המלצות חדשות.</div>')
    else:
        banner = ""

    # ---- today
    if st["status"] != "active":
        today = ""
    elif upcoming:
        today = (f'<div class="sum">{len(upcoming)} הימורים · להשקיע <b>{_ils(total_stake)}</b> · '
                 f'אם הכול מצליח <b class="win">{_ils(max_win)}</b></div>'
                 + "".join(_ticket(r) for r in upcoming))
    elif picks_today:
        today = ('<div class="empty"><b>היום לא מהמרים.</b><br>בדקנו את כל האפשרויות בווינר — '
                 'אף אחת לא שווה את הסיכון. ככה זה רוב הימים, וזה בסדר.</div>')
    else:
        today = ('<div class="empty"><b>ההמלצות להיום עוד לא מוכנות.</b><br>'
                 'כתוב ל-Claude <b>picks</b> והוא ימשוך את היחסים של ווינר ויעדכן כאן.</div>')
    if running:
        today += '<h3>במשחק עכשיו</h3>' + "".join(_ticket(r) for r in running)

    pct = st["progress"] * 100
    wl = st["wins"] + st["losses"]
    hit = f"{st['wins'] / wl:.0%}" if wl else "—"
    upd = now.astimezone(TZ).strftime("%d/%m %H:%M")
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1116">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>{e(config.PROJECT_NAME)}</title>
<style>
:root{{--bg:#0e1116;--card:#171b22;--line:#262b35;--tx:#eef0f4;--mut:#98a0b0;--win:#2ec27e;--loss:#ef5a5a;--acc:#4c8dff;--warn:#f0b429}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
main{{max-width:560px;margin:0 auto;padding:16px 14px calc(40px + env(safe-area-inset-bottom))}}
h1{{font-size:20px;margin:4px 0 2px}}h2{{font-size:18px;margin:26px 0 10px}}h3{{font-size:15px;margin:18px 0 8px;color:var(--mut)}}
.muted{{color:var(--mut)}}.win{{color:var(--win)}}.loss{{color:var(--loss)}}
.hero{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin-top:12px}}
.bal{{font-size:34px;font-weight:800;letter-spacing:-.5px}}
.sub{{color:var(--mut);font-size:14px}}
.bar{{height:10px;background:#252b36;border-radius:99px;overflow:hidden;margin:12px 0 6px}}
.bar i{{display:block;height:100%;background:var(--win);border-radius:99px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:12px}}
.stats div{{background:#1d222b;border-radius:10px;padding:8px 4px;text-align:center}}
.stats span{{display:block;font-size:11px;color:var(--mut)}}.stats b{{font-size:15px}}
.spark{{width:100%;height:56px;margin-top:10px}}.spark .base{{stroke:#394050;stroke-dasharray:4 4}}
.banner{{border-radius:12px;padding:12px 14px;margin-top:12px;font-weight:600}}
.banner.good{{background:#123524;color:#7ee2b0}}.banner.bad{{background:#3a1717;color:#ffb3b3}}
.sum{{background:#13233d;border-radius:12px;padding:10px 12px;margin-bottom:10px;font-size:15px}}
.ticket{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:10px 0}}
.tag{{display:inline-block;font-size:12px;font-weight:700;padding:3px 10px;border-radius:99px}}
.tag.single{{background:#1f3254;color:#9cc0ff}}.tag.parlay{{background:#3b2a55;color:#d2b6ff}}
.leg{{padding:10px 0;border-bottom:1px dashed var(--line)}}.leg:last-of-type{{border-bottom:0}}
.game{{font-size:13px;color:var(--mut)}}
.bet{{font-size:17px;font-weight:700;margin:2px 0}}
.odds{{font-size:13px;font-weight:600;background:#232935;border-radius:6px;padding:1px 6px;margin-inline-start:4px}}
.hint{{font-size:13px;color:#b9c3d6;background:#1d222b;border-radius:8px;padding:6px 8px;margin-top:4px}}
.conf{{font-size:13px;color:var(--mut);margin-top:4px}}
.warn{{font-size:13px;color:var(--warn);margin-top:4px}}
.nums{{display:grid;grid-template-columns:1fr 1fr 1.3fr;gap:6px;margin-top:10px}}
.nums div{{background:#1d222b;border-radius:10px;padding:8px;text-align:center}}
.nums span{{display:block;font-size:11px;color:var(--mut)}}.nums b{{font-size:17px}}
.reason{{font-size:13px;color:var(--mut);margin-top:10px}}
.empty{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;text-align:center;line-height:1.7}}
.day{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 12px;margin:8px 0}}
.dh{{display:flex;justify-content:space-between;margin-bottom:4px}}
.day ul{{list-style:none;margin:0;padding:0}}
.day li{{display:grid;grid-template-columns:22px 1fr;gap:2px 6px;padding:6px 0;border-top:1px solid var(--line);font-size:14px}}
.day li .am{{grid-column:2;font-size:12px;color:var(--mut)}}
.day li.w .ic{{color:var(--win)}}.day li.l .ic{{color:var(--loss)}}.day li.o .ic{{color:var(--warn)}}
details{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-top:10px}}
summary{{cursor:pointer;font-weight:600}}details p,details li{{font-size:14px;color:#c9cfdb}}
footer{{margin-top:24px;font-size:12px;color:var(--mut);text-align:center}}
a{{color:var(--acc)}}
</style></head><body><main>
<h1>{e(config.PROJECT_NAME)}</h1>
<div class="muted" style="font-size:13px">עודכן {upd}{' · יחסי ווינר נמשכו ' + datetime.fromisoformat(picks_at).astimezone(TZ).strftime('%d/%m %H:%M') if picks_at else ''}</div>
{banner}
<section class="hero">
  <div class="sub">יתרה נוכחית</div>
  <div class="bal {'win' if st['pnl'] > 0 else 'loss' if st['pnl'] < 0 else ''}">{_ils(st['balance'])}</div>
  <div class="sub">התחלה {_ils(config.START_BALANCE)} · מטרה {_ils(st['target_bal'])} · עצירה ב-{_ils(st['floor_bal'])}</div>
  <div class="bar"><i style="width:{pct:.0f}%"></i></div>
  <div class="sub">{pct:.0f}% מהדרך למטרה (רווח {_ils(st['pnl'], sign=True)} מתוך {_ils(config.PROFIT_TARGET)})</div>
  {_spark(st['history'])}
  <div class="stats">
    <div><span>ניצחונות</span><b class="win">{st['wins']}</b></div>
    <div><span>הפסדים</span><b class="loss">{st['losses']}</b></div>
    <div><span>אחוז הצלחה</span><b>{hit}</b></div>
    <div><span>בהימורים פתוחים</span><b>{_ils(st['open_stake'])}</b></div>
  </div>
</section>

<h2>מה לשים היום</h2>
{today}

<h2>היסטוריה</h2>
{_history(settled)}

<details><summary>איך זה עובד?</summary>
<ul>
<li>כל יום המערכת בונה תחזית לכל משחק NBA: חוזק הקבוצות מהעונה הנוכחית והקודמת, יתרון ביתיות, עייפות (משחק יום אחרי יום), פציעות, ומה שהשוק המקצועי בארה"ב חושב.</li>
<li>היא משווה את התחזית ליחסים של ווינר וממליצה רק כשווינר משלם יותר ממה שהסיכוי האמיתי מצדיק. ברוב הימים אין כאלה.</li>
<li>הסכום לכל הימור מחושב מהיתרה הנוכחית (שיטת קלי מוקטנת): עד {config.MAX_SINGLE_STAKE_PCT:.0%} מהיתרה להימור בודד, עד {config.MAX_PARLAY_STAKE_PCT:.0%} לפרליי, ולא יותר מ-{config.DAILY_MAX_EXPOSURE:.0%} מהיתרה ביום אחד. כשמרוויחים הסכומים גדלים, כשמפסידים הם קטנים.</li>
<li>הכול לפי כללי ווינר: פרליי של 2–{config.PARLAY_MAX_LEGS} משחקים שונים (ווינר מתיר 2–10, ולא מתיר שני הימורים מאותו משחק באותו טופס). כל שווקי משחקי ה-NBA מסומנים בווינר SD — מותר לשחק אותם כבודדים.</li>
<li>המעקב מניח ששמת בדיוק את מה שמופיע כאן. משחק שבוטל נחשב ביחס 1.</li>
<li>הפרויקט נעצר אוטומטית כשמגיעים למטרה או כשהיתרה יורדת ל-{_ils(st['floor_bal'])}.</li>
</ul></details>
<details><summary>חשוב לדעת</summary>
<p>ווינר לוקח מרווח של כ-11%–14% על כל הימור, וזה הרבה. גם עם מודל טוב, תקופות הפסד ארוכות הן נורמליות. הימר רק בכסף שאתה מוכן להפסיד, ואל תגדיל סכומים כדי "להחזיר" הפסד.</p>
</details>
<footer>{e(config.PROJECT_NAME)} · <a href="reports/latest_full.html">ניתוח מלא (טכני)</a></footer>
</main></body></html>"""
