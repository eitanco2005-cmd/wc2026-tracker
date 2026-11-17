"""Combine Winner prices, sharp market and model into EV-graded bets."""
from datetime import timedelta

from . import config
from .pricing import (devig2, ev, kelly, margin_of, mu_from_ml, mu_from_spread,
                      mu_from_total, p_cover, p_over)
from .teams import ABBR_TO_HE, ABBR_TO_NAME


def match_games(winner_markets, espn_games):
    """Group Winner markets per ESPN game. Returns {espn_id: (game, [markets])}."""
    out = {}
    for m in winner_markets:
        best = None
        for g in espn_games:
            if {g["home"], g["away"]} != {m["home"], m["away"]}:
                continue
            if m["start"] and abs(g["start"] - m["start"]) > timedelta(hours=14):
                continue
            best = g
        if not best:
            continue
        if best["home"] != m["home"]:       # Winner listed teams the other way round
            m = dict(m, home=best["home"], away=best["away"],
                     outcomes=[dict(o, side={"home": "away", "away": "home"}.get(o["side"], o["side"]))
                               for o in m["outcomes"]])
        out.setdefault(best["id"], (best, []))[1].append(m)
    return out


def market_projection(odds, sd):
    """Expected home margin & total from DraftKings lines (de-vigged)."""
    if not odds:
        return None, None
    mus = []
    if odds.get("spread_home_odds") and odds.get("spread_away_odds"):
        ph, _, _ = devig2(odds["spread_home_odds"], odds["spread_away_odds"])
        mus.append(mu_from_spread(odds["spread_home_line"], ph, sd["FG_margin"]))
    if odds.get("ml_home") and odds.get("ml_away"):
        ph, _, _ = devig2(odds["ml_home"], odds["ml_away"])
        mus.append(mu_from_ml(ph, sd["FG_margin"]))
    margin = sum(mus) / len(mus) if mus else None
    total = None
    if odds.get("over_odds") and odds.get("under_odds") and odds.get("total_line"):
        po, _, _ = devig2(odds["over_odds"], odds["under_odds"])
        total = mu_from_total(odds["total_line"], po, sd["FG_total"])
    return margin, total


def blend(market, model):
    if market is None:
        return model, False
    return config.MARKET_WEIGHT * market + (1 - config.MARKET_WEIGHT) * model, True


def evaluate_game(game, markets, model, inj_home, inj_away):
    proj = project(game, model, inj_home, inj_away)
    return proj, evaluate(game, markets, proj, model.sd, model.frac)


def project(game, model, inj_home, inj_away):
    sd = model.sd
    pm = model.predict(game["home"], game["away"], game["start"], game.get("neutral"),
                       inj_home, inj_away)
    mk_margin, mk_total = market_projection(game.get("odds"), sd)
    margin, anchored_m = blend(mk_margin, pm["margin"])
    total, anchored_t = blend(mk_total, pm["total"])
    gap_m = mk_margin is not None and abs(mk_margin - pm["margin"]) > config.MAX_MODEL_GAP_MARGIN
    gap_t = mk_total is not None and abs(mk_total - pm["total"]) > config.MAX_MODEL_GAP_TOTAL
    proj = dict(gap_margin=gap_m, gap_total=gap_t,
                model_margin=pm["margin"], model_total=pm["total"],
                market_margin=mk_margin, market_total=mk_total,
                margin=margin, total=total, home_pts=(total + margin) / 2,
                away_pts=(total - margin) / 2, b2b_home=pm["b2b_home"], b2b_away=pm["b2b_away"],
                anchored_m=anchored_m, anchored_t=anchored_t)
    return proj


def evaluate(game, markets, proj, sd, fr):
    anomalies = line_anomalies(markets, fr)
    proj["anomalies"] = sorted(set(anomalies.values()))
    margin, total = proj["margin"], proj["total"]
    anchored_m, anchored_t = proj["anchored_m"], proj["anchored_t"]
    gap_m, gap_t = proj["gap_margin"], proj["gap_total"]
    bets = []
    for m in markets:
        per, kind = m["period"], m["kind"]
        if kind == "player_points":
            bets += _prop_bets(game, m, proj)
            continue
        if kind in ("spread", "ml"):
            if per == "FG":
                mu, s = margin, sd["FG_margin"]
            else:
                mu, s = fr[f"{per}_margin"] * margin, sd[f"{per}_margin"]
            anchored = anchored_m
        elif kind == "total":
            if per == "FG":
                mu, s = total, sd["FG_total"]
            else:
                mu, s = fr[f"{per}_total"] * total, sd[f"{per}_total"]
            anchored = anchored_t
        elif kind == "team_total" and per == "FG":
            mu = proj["home_pts"] if m["team"] == game["home"] else proj["away_pts"]
            s, anchored = sd["team_pts"], anchored_m and anchored_t
        else:
            continue

        tier = "A" if per == "FG" and kind in ("spread", "total", "ml") else "C" if per == "Q1" else "B"
        if not anchored:
            tier = {"A": "B", "B": "C", "C": "C"}[tier]
        vig = margin_of([o["odds"] for o in m["outcomes"]])
        for o in m["outcomes"]:
            if kind in ("spread", "ml"):
                team_mu = mu if o["side"] == "home" else -mu
                p = p_cover(o["line"], team_mu, s)
                team = game[o["side"]]
            else:
                po = p_over(o["line"], mu, s)
                p = po if o["side"] == "over" else 1 - po
                team = m.get("team")
            e = ev(p, o["odds"])
            blocked = (gap_m and kind in ("spread", "ml", "team_total")) or \
                      (gap_t and kind in ("total", "team_total"))
            bets.append(dict(
                game_id=game["id"], home=game["home"], away=game["away"], start=game["start"],
                market=_market_name(m), kind=kind, period=per, side=o["side"], team=team,
                line=o["line"], odds=o["odds"], label=o["label"], p=p, ev=e,
                kelly=kelly(p, o["odds"]), tier=tier, vig=vig, mu=mu, sd=s,
                blocked=blocked, qualifies=e >= config.MIN_EV[tier] and not blocked, winner_mid=m["mid"], flag=m.get("flag"),
                anomaly=anomalies.get(m["mid"])))
    return bets


def _prop_bets(game, m, proj):
    """Player points over/under: own projection only (no sharp market for props) -> tier P."""
    from .players import match, p_side
    pl = match(m.get("player_he", ""), proj.get("players") or [])
    if not pl:
        proj.setdefault("unmatched_players", []).append(m.get("player_disp") or m.get("player_he"))
        return []
    status = (pl.get("status") or "").lower()
    healthy = status == "" or any(s and s in status for s in config.PROP_OK_STATUS)
    vig = margin_of([o["odds"] for o in m["outcomes"]])
    out = []
    for o in m["outcomes"]:
        p = p_side(o["side"], o["line"], pl["mu"], pl["sd"])
        e = ev(p, o["odds"])
        blocked = (not healthy or pl["min"] < config.PROP_MIN_MINUTES
                   or abs(pl["mu"] - o["line"]) > config.PROP_MAX_GAP or proj.get("gap_total"))
        out.append(dict(
            game_id=game["id"], home=game["home"], away=game["away"], start=game["start"],
            market=_market_name(m), kind="player_points", period="FG", side=o["side"], team=pl["team"],
            line=o["line"], odds=o["odds"], label=o["label"], p=p, ev=e, kelly=kelly(p, o["odds"]),
            tier="P", vig=vig, mu=pl["mu"], sd=pl["sd"], blocked=bool(blocked),
            qualifies=e >= config.MIN_EV["P"] and not blocked, winner_mid=m["mid"], flag=m.get("flag"),
            anomaly=None, player=m.get("player_disp") or m.get("player_he"), athlete_id=pl["athlete_id"],
            player_en=pl["name"], player_status=status))
    return out


_PER_HE = {"FG": "משחק מלא", "H1": "מחצית ראשונה", "Q1": "רבע ראשון"}
_KIND_HE = {"spread": "הימור יתרון", "total": "מעל/מתחת", "team_total": "סך נקודות קבוצתי",
            "ml": "מנצחת", "player_points": "נקודות שחקן"}


def _market_name(m):
    n = f"{_KIND_HE[m['kind']]} – {_PER_HE[m['period']]}"
    if m["kind"] == "player_points":
        return f"{n} ({m.get('player_disp') or m.get('player_he', '')})"
    if not m.get("mp") and m["kind"] != "team_total":
        return n
    if m["kind"] == "team_total":
        n += f" ({m['home_he'] if m['team'] == m['home'] else m['away_he']})"
    return n


def stake_for(p_kelly, cap_pct):
    s = config.BANKROLL * min(config.KELLY_FRACTION * p_kelly, cap_pct)
    return max(round(s / 5) * 5, config.MIN_STAKE) if s > 0 else 0.0


def team_name(abbr):
    return ABBR_TO_NAME.get(abbr, abbr)


def price_sheet(game, model, inj_home, inj_away):
    """Without Winner odds: lookup table. For each market and each line near the projection,
    the minimum decimal odds each side needs to clear the EV threshold."""
    proj, _ = evaluate_game(game, [], model, inj_home, inj_away)
    fr = model.frac
    base = dict(home=game["home"], away=game["away"], home_he=game["home"], away_he=game["away"],
                start=game["start"], flag=None, mp="")
    synth = []
    for per, mf, tf in (("FG", 1.0, 1.0), ("H1", fr["H1_margin"], fr["H1_total"]),
                        ("Q1", fr["Q1_margin"], fr["Q1_total"])):
        hl = round(-proj["margin"] * mf) + 0.5          # home handicap near fair
        for L in [hl + k for k in range(-2, 3)]:
            synth.append(dict(base, mid=f"{per}|spread|{L}", period=per, kind="spread",
                              outcomes=[dict(label="", side="home", line=L, odds=1.0),
                                        dict(label="", side="away", line=-L, odds=1.0)]))
        tl = round(proj["total"] * tf) + 0.5
        for L in [tl + k for k in range(-2, 3)]:
            synth.append(dict(base, mid=f"{per}|total|{L}", period=per, kind="total",
                              outcomes=[dict(label="", side="over", line=L, odds=1.0),
                                        dict(label="", side="under", line=L, odds=1.0)]))
    _, bets = evaluate_game(game, synth, model, inj_home, inj_away)
    sheet = {}
    for b in bets:
        per, kind, L = b["winner_mid"].split("|")
        key = (per, kind)
        row = sheet.setdefault(key, {}).setdefault(float(L), {"tier": b["tier"], "blocked": b["blocked"]})
        row[b["side"]] = ((1 + config.MIN_EV[b["tier"]]) / b["p"], b["p"])
    return proj, sheet


# Winner's half/quarter lines vs its own full-game line
ANOMALY_PTS = {("H1", "total"): 3.0, ("Q1", "total"): 2.0, ("H1", "spread"): 2.5, ("Q1", "spread"): 2.0}
SPREAD_FRAC = {"H1": 0.5, "Q1": 0.25}


def line_anomalies(markets, frac):
    """{mid: note} for H1/Q1 markets whose line is far from what Winner's own FG line implies."""
    fg = {}
    for m in markets:
        if m["period"] == "FG" and m["kind"] in ("spread", "total"):
            home = next((o for o in m["outcomes"] if o["side"] in ("home", "over")), m["outcomes"][0])
            fg[m["kind"]] = home["line"]
    out = {}
    for m in markets:
        key = (m["period"], m["kind"])
        if key not in ANOMALY_PTS or m["kind"] not in fg:
            continue
        o = next((o for o in m["outcomes"] if o["side"] in ("home", "over")), m["outcomes"][0])
        if m["kind"] == "total":
            implied = fg["total"] * frac[f"{m['period']}_total"]
            what = "סך"
        else:
            implied = fg["spread"] * SPREAD_FRAC[m["period"]]
            what = "יתרון"
        diff = o["line"] - implied
        if abs(diff) >= ANOMALY_PTS[key]:
            per = "מחצית" if m["period"] == "H1" else "רבע"
            out[m["mid"]] = (f"קו {what} ה{per} של ווינר ({o['line']:g}) רחוק {abs(diff):.1f} נק' ממה שקו המשחק המלא "
                             f"שלהם מרמז ({implied:.1f}). או טעות תמחור של ווינר, או שהם יודעים משהו — בדוק לפני.")
    return out
