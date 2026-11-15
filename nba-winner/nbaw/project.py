"""Bankroll project: balance, target, stop-loss, stake sizing, history."""
import json
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TZ)


def state(rows):
    settled = [r for r in rows if r.get("result")]
    open_ = [r for r in rows if not r.get("result")]
    pnl = sum(float(r["pnl"] or 0) for r in settled)
    balance = config.START_BALANCE + pnl
    open_stake = sum(float(r["stake"] or 0) for r in open_)
    target_bal = config.START_BALANCE + config.PROFIT_TARGET
    floor_bal = config.START_BALANCE * (1 - config.STOP_LOSS_PCT)
    wins = sum(r["result"] == "W" for r in settled)
    losses = sum(r["result"] == "L" for r in settled)
    staked = sum(float(r["stake"] or 0) for r in settled)
    # balance history by settle day (day of last leg)
    hist = OrderedDict()
    hist[config.PROJECT_START_DATE] = config.START_BALANCE
    run = config.START_BALANCE
    for r in sorted(settled, key=_day):
        run += float(r["pnl"] or 0)
        hist[_day(r)] = run
    status = "active"
    if balance >= target_bal:
        status = "target"
    elif balance <= floor_bal:
        status = "stopped"
    return dict(balance=balance, pnl=pnl, open_stake=open_stake, available=balance - open_stake,
                target_bal=target_bal, floor_bal=floor_bal, wins=wins, losses=losses,
                pushes=len(settled) - wins - losses, staked=staked,
                roi=pnl / staked if staked else 0.0,
                progress=max(0.0, min(1.0, pnl / config.PROFIT_TARGET)) if config.PROFIT_TARGET else 0,
                history=list(hist.items()), status=status, n_open=len(open_))


def _day(r):
    try:
        legs = json.loads(r["legs_json"])
        st = max(datetime.fromisoformat(l["start"]) for l in legs)
        return st.astimezone(TZ).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return r["created"][:10]


def stake(balance, kelly_f, cap_pct):
    s = balance * min(config.KELLY_FRACTION * kelly_f, cap_pct)
    if s <= 0:
        return 0
    return max(int(round(s)), int(config.MIN_STAKE))


def size_day(balance, singles, parlays):
    """Stakes for today's tickets, scaled down to the daily exposure cap."""
    out_s = [(b, stake(balance, b["kelly"], config.MAX_SINGLE_STAKE_PCT)) for b in singles]
    out_p = [(p, stake(balance, p["kelly"], config.MAX_PARLAY_STAKE_PCT)) for p in parlays]
    total = sum(s for _, s in out_s) + sum(s for _, s in out_p)
    cap = balance * config.DAILY_MAX_EXPOSURE
    if total > cap and total > 0:
        f = cap / total
        out_s = [(b, max(int(config.MIN_STAKE), int(s * f))) for b, s in out_s]
        out_p = [(p, max(int(config.MIN_STAKE), int(s * f))) for p, s in out_p]
    return out_s, out_p
