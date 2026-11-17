"""Build parlays only from positive-EV legs, one leg per game (independent)."""
from itertools import combinations
from math import prod

from . import config
from .pricing import kelly


def build(bets, allow_negative=False):
    pool = [b for b in bets if b["qualifies"]] if not allow_negative else \
        [b for b in bets if not b.get("blocked")]
    pool = [b for b in pool if b.get("kind") != "player_points"]  # props: singles only (model-only, riskier)
    # best leg per game
    best = {}
    for b in sorted(pool, key=lambda x: -x["ev"]):
        best.setdefault(b["game_id"], b)
    legs = sorted(best.values(), key=lambda x: -x["ev"])[: config.PARLAY_POOL]
    out = []
    for k in range(config.PARLAY_MIN_LEGS, config.PARLAY_MAX_LEGS + 1):
        for combo in combinations(legs, k):
            p = prod(b["p"] for b in combo)
            odds = prod(b["odds"] for b in combo)
            if p < config.PARLAY_MIN_PROB:
                continue
            e = p * odds - 1
            if e <= 0 and not allow_negative:
                continue
            out.append(dict(legs=combo, p=p, odds=odds, ev=e, kelly=kelly(p, odds)))
    # rank by growth (EV weighted by probability) rather than raw EV
    out.sort(key=lambda x: -(x["ev"] * x["p"] ** 0.5))
    seen, final = set(), []
    for par in out:
        key = frozenset((l["game_id"]) for l in par["legs"])
        if key in seen:
            continue
        seen.add(key)
        final.append(par)
        if len(final) >= config.PARLAY_TOP_N:
            break
    return final
