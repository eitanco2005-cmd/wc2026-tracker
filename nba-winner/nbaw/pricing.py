"""Probability / odds math."""
from statistics import NormalDist

N = NormalDist()


def american_to_decimal(a) -> float | None:
    try:
        a = float(str(a).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + (a / 100 if a > 0 else 100 / -a)


def devig2(d1: float, d2: float):
    """Proportional de-vig of a two-way market -> (p1, p2, margin)."""
    i1, i2 = 1 / d1, 1 / d2
    s = i1 + i2
    return i1 / s, i2 / s, s - 1


def _clip(p):
    return min(max(p, 1e-4), 1 - 1e-4)


def mu_from_spread(home_line: float, p_home_cover: float, sd: float) -> float:
    """Home covers if margin + home_line > 0. Returns expected home margin."""
    return -home_line + sd * N.inv_cdf(_clip(p_home_cover))


def mu_from_ml(p_home_win: float, sd: float) -> float:
    return sd * N.inv_cdf(_clip(p_home_win))


def mu_from_total(line: float, p_over: float, sd: float) -> float:
    return line + sd * N.inv_cdf(_clip(p_over))


def p_over(line: float, mu: float, sd: float) -> float:
    """P(X > line) for a half-point line (continuity already implied)."""
    return 1 - N.cdf((line - mu) / sd)


def p_cover(team_line: float, team_mu_margin: float, sd: float) -> float:
    """P(team margin + team_line > 0)."""
    return 1 - N.cdf((-team_line - team_mu_margin) / sd)


def ev(p: float, odds: float) -> float:
    return p * odds - 1


def kelly(p: float, odds: float) -> float:
    b = odds - 1
    return max(0.0, (p * odds - 1) / b) if b > 0 else 0.0


def margin_of(prices) -> float:
    return sum(1 / x for x in prices) - 1
