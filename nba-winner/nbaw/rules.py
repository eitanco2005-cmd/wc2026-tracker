"""Winner ticket rules (winner.co.il 'כללי משחק ווינר ליין', checked 15/11/2026).

- Combination: 2-10 selections per ticket.
- NBA game markets are marked SD -> allowed as single, double, or more (verified in Winner UI).
- Options related to the same event cannot be combined in one combination.
- A cancelled game is settled at odds 1.
"""
MIN_COMBO, MAX_COMBO = 2, 10


def single_ok(bet):
    return bet.get("kind") in ("spread", "total", "team_total", "ml")  # all SD on NBA games


def parlay_problems(legs):
    probs = []
    if not MIN_COMBO <= len(legs) <= MAX_COMBO:
        probs.append(f"מספר בחירות {len(legs)} מחוץ לטווח {MIN_COMBO}-{MAX_COMBO}")
    games = [l["game_id"] for l in legs]
    if len(set(games)) != len(games):
        probs.append("שתי בחירות מאותו משחק — אסור בווינר")
    return probs
