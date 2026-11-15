"""Team-strength model: recency-weighted ridge ratings for margin and scoring,
back-to-back effect learned from data, injury adjustments, and calibration of
distribution widths / half & quarter fractions from historical line scores."""
import math
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

from . import config
from .teams import ABBR_TO_NAME


class Model:
    def __init__(self, games, ref_time: datetime):
        self.games = sorted(games, key=lambda g: g["start"])
        self.ref = ref_time
        self.teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
        self.idx = {t: i for i, t in enumerate(self.teams)}
        self.last_played = defaultdict(list)
        for g in self.games:
            self.last_played[g["home"]].append(g["start"])
            self.last_played[g["away"]].append(g["start"])
        self.sd = dict(config.DEFAULT_SD)
        self.frac = dict(config.DEFAULT_FRAC)
        self.cur_gp = defaultdict(int)
        for g in self.games:
            if g["current"]:
                self.cur_gp[g["home"]] += 1
                self.cur_gp[g["away"]] += 1
        self._fit()
        self._calibrate()

    # ---------------------------------------------------------------- utils
    def _weight(self, g):
        if not g["current"]:
            return config.PRIOR_SEASON_WEIGHT
        age = (self.ref - g["start"]).total_seconds() / 86400
        return 0.5 ** (age / config.HALF_LIFE_DAYS)

    def is_b2b(self, team, when: datetime):
        prev = [t for t in self.last_played[team] if t < when - timedelta(hours=3)]
        return bool(prev) and (when - prev[-1]) < timedelta(hours=36)

    # ---------------------------------------------------------------- fit
    def _fit(self):
        n = len(self.teams)
        rows_m, y_m, w_m = [], [], []
        rows_p, y_p, w_p = [], [], []
        for g in self.games:
            w = self._weight(g)
            hi, ai = self.idx[g["home"]], self.idx[g["away"]]
            hca = 0.0 if g.get("neutral") else 1.0
            b2b = float(self.is_b2b(g["home"], g["start"])) - float(self.is_b2b(g["away"], g["start"]))
            # margin: [hca, b2b_diff, team ratings...]
            x = np.zeros(2 + n)
            x[0], x[1], x[2 + hi], x[2 + ai] = hca, b2b, 1, -1
            rows_m.append(x); y_m.append(g["hs"] - g["as"]); w_m.append(w)
            # points: [const, home_flag, off(n), def(n)]
            for us, them, pts, home in ((hi, ai, g["hs"], hca), (ai, hi, g["as"], 0.0)):
                xp = np.zeros(2 + 2 * n)
                xp[0], xp[1], xp[2 + us], xp[2 + n + them] = 1, home, 1, 1
                rows_p.append(xp); y_p.append(pts); w_p.append(w)

        self.beta_m = self._ridge(np.array(rows_m), np.array(y_m), np.array(w_m), unpen=2)
        self.beta_p = self._ridge(np.array(rows_p), np.array(y_p), np.array(w_p), unpen=2)
        self.hca = self.beta_m[0]
        self.b2b_coef = self.beta_m[1]

    @staticmethod
    def _ridge(X, y, w, unpen):
        W = w[:, None]
        A = X.T @ (W * X)
        lam = np.full(X.shape[1], config.RIDGE_LAMBDA)
        lam[:unpen] = 1e-6
        A += np.diag(lam)
        return np.linalg.solve(A, X.T @ (w * y))

    def rating(self, t):
        return self.beta_m[2 + self.idx[t]] if t in self.idx else 0.0

    # ---------------------------------------------------------------- predict
    def predict(self, home, away, when: datetime, neutral=False, inj_home=0.0, inj_away=0.0):
        n = len(self.teams)
        hca = 0.0 if neutral else 1.0
        b2b_h, b2b_a = self.is_b2b(home, when), self.is_b2b(away, when)
        margin = (self.hca * hca + self.b2b_coef * (float(b2b_h) - float(b2b_a))
                  + self.rating(home) - self.rating(away))
        bp = self.beta_p
        hp = bp[0] + bp[1] * hca + bp[2 + self.idx.get(home, 0)] + bp[2 + n + self.idx.get(away, 0)]
        ap = bp[0] + bp[2 + self.idx.get(away, 0)] + bp[2 + n + self.idx.get(home, 0)]
        # make scoring model consistent with the margin model
        total = hp + ap
        # injuries: own offence drops, opponent's slightly rises
        margin -= inj_home - inj_away
        total -= 0.4 * (inj_home + inj_away)
        return dict(margin=margin, total=total, home_pts=(total + margin) / 2,
                    away_pts=(total - margin) / 2, b2b_home=b2b_h, b2b_away=b2b_a)

    # ---------------------------------------------------------------- calibrate
    def _calibrate(self):
        """Estimate residual SDs and half/quarter fractions from this + last season."""
        res = defaultdict(list)
        sums = defaultdict(float)
        for g in self.games:
            if len(g.get("hq", [])) < 4 or len(g.get("aq", [])) < 4:
                continue
            p = self.predict(g["home"], g["away"], g["start"], g.get("neutral"))
            m, t = g["hs"] - g["as"], g["hs"] + g["as"]
            res["FG_margin"].append(m - p["margin"])
            res["FG_total"].append(t - p["total"])
            res["team_pts"] += [g["hs"] - p["home_pts"], g["as"] - p["away_pts"]]
            h1m = sum(g["hq"][:2]) - sum(g["aq"][:2]); h1t = sum(g["hq"][:2]) + sum(g["aq"][:2])
            q1m = g["hq"][0] - g["aq"][0]; q1t = g["hq"][0] + g["aq"][0]
            reg_t = sum(g["hq"][:4]) + sum(g["aq"][:4])
            for k, v in (("H1_total", h1t), ("Q1_total", q1t)):
                sums[k] += v
            sums["reg_total"] += reg_t
            sums["pred_margin_sq"] += p["margin"] ** 2
            sums["h1m_x_pm"] += h1m * p["margin"]; sums["q1m_x_pm"] += q1m * p["margin"]
            res["_h1m"].append((h1m, p["margin"])); res["_q1m"].append((q1m, p["margin"]))
            res["_h1t"].append(h1t); res["_q1t"].append(q1t); res["_pt"].append(p["total"])
        if len(res["FG_margin"]) < 200:
            return
        for k in ("FG_margin", "FG_total", "team_pts"):
            self.sd[k] = float(np.std(res[k]))
        if sums["pred_margin_sq"] > 0:
            self.frac["H1_margin"] = sums["h1m_x_pm"] / sums["pred_margin_sq"]
            self.frac["Q1_margin"] = sums["q1m_x_pm"] / sums["pred_margin_sq"]
        self.frac["H1_total"] = sums["H1_total"] / sums["reg_total"]
        self.frac["Q1_total"] = sums["Q1_total"] / sums["reg_total"]
        self.sd["H1_margin"] = float(np.std([a - self.frac["H1_margin"] * b for a, b in res["_h1m"]]))
        self.sd["Q1_margin"] = float(np.std([a - self.frac["Q1_margin"] * b for a, b in res["_q1m"]]))
        self.sd["H1_total"] = float(np.std([a - self.frac["H1_total"] * b for a, b in zip(res["_h1t"], res["_pt"])]))
        self.sd["Q1_total"] = float(np.std([a - self.frac["Q1_total"] * b for a, b in zip(res["_q1t"], res["_pt"])]))

    def ratings_table(self):
        rows = []
        for t in self.teams:
            rows.append((t, ABBR_TO_NAME.get(t, t), self.rating(t), self.cur_gp[t]))
        return sorted(rows, key=lambda r: -r[2])


# ---------------------------------------------------------------- injuries
def player_impact(stats, team_gp):
    """Rough points-per-game value of a player over a replacement, from box-score averages."""
    if not stats:
        return 0.0
    gp = stats.get("gamesPlayed", 0)
    mins = stats.get("avgMinutes", 0)
    if gp < 3 or mins < 12:
        return 0.0
    # Already-missing players are baked into the ratings
    if team_gp and gp / team_gp < 0.4:
        return 0.0
    val = (stats.get("avgPoints", 0) + 0.7 * stats.get("avgAssists", 0)
           + 0.35 * stats.get("avgRebounds", 0)
           + 0.7 * (stats.get("avgSteals", 0) + stats.get("avgBlocks", 0))
           - 0.7 * stats.get("avgTurnovers", 0))
    return max(0.0, (val - 0.45 * mins) * 0.28)


def team_injury_impact(inj_list, team_gp, stats_fn):
    total, detail = 0.0, []
    for p in inj_list:
        w = 0.0
        for k, v in config.INJURY_WEIGHT.items():
            if k in p["status"]:
                w = v
                break
        if w == 0:
            continue
        imp = player_impact(stats_fn(p["athlete_id"]), team_gp)
        if imp > 0.05:
            total += w * imp
            detail.append(dict(name=p["name"], status=p["status"], impact=round(w * imp, 1)))
    return min(total, config.INJURY_TEAM_CAP), detail


def sigmoid(x):
    return 1 / (1 + math.exp(-x))
