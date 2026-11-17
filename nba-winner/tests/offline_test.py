"""Offline end-to-end test: real Winner + ESPN fixtures, synthetic results history."""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FX = ROOT / "tests" / "fixtures"

from nbaw import config, espn  # noqa: E402
from nbaw.teams import TEAMS  # noqa: E402

config.DATA_DIR = ROOT / "tests" / "_out" / "data"
config.REPORTS_DIR = ROOT / "tests" / "_out" / "reports"
config.CACHE_DIR = ROOT / "tests" / "_out" / "cache"
config.ROOT = ROOT / "tests" / "_out"   # keep the real site index.html untouched

NOW = datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc)
random.seed(7)
ABBRS = [t[0] for t in TEAMS]
TRUE = {a: random.gauss(0, 5) for a in ABBRS}
OFF = {a: random.gauss(0, 3) for a in ABBRS}


def synth():
    games = []
    for season, start, n_days, cur in ((2026, datetime(2025, 10, 21, 23, tzinfo=timezone.utc), 170, False),
                                       (2027, datetime(2026, 10, 20, 23, tzinfo=timezone.utc), 26, True)):
        for d in range(n_days):
            day = start + timedelta(days=d)
            teams = random.sample(ABBRS, 14)
            for i in range(0, 14, 2):
                h, a = teams[i], teams[i + 1]
                mu = 2.5 + TRUE[h] - TRUE[a]
                tot = 226 + 2 * (OFF[h] + OFF[a])
                m = random.gauss(mu, 12); t = random.gauss(tot, 17)
                hs, as_ = round((t + m) / 2), round((t - m) / 2)
                def q(x):
                    w = [random.uniform(.22, .28) for _ in range(4)]; s = sum(w)
                    v = [round(x * x_ / s) for x_ in w]; v[-1] += x - sum(v); return v
                games.append(dict(id=f"{season}{d}{i}", start=day, season=season, stype=2, home=h, away=a,
                                  completed=True, neutral=False, hs=float(hs), as_=0, hq=q(hs), aq=q(as_),
                                  current=cur) | {"as": float(as_)})
    return games


espn.history = lambda today, progress=print: synth()
espn.todays_games = lambda now: [espn.parse_event(e) for e in json.load(open(FX / "espn_today.json"))["events"]]
espn.injuries = lambda: {"Indiana Pacers": [dict(name="Star Guard", athlete_id="1", status="out", comment="")],
                         "Los Angeles Lakers": [dict(name="Big Man", athlete_id="2", status="questionable", comment="")]}
espn.athlete_stats = lambda aid: {"1": dict(gamesPlayed=12, avgMinutes=34, avgPoints=24, avgAssists=8, avgRebounds=5,
                                            avgSteals=1.2, avgBlocks=.4, avgTurnovers=3),
                                  "2": dict(gamesPlayed=11, avgMinutes=31, avgPoints=19, avgAssists=3, avgRebounds=11,
                                            avgSteals=.8, avgBlocks=1.5, avgTurnovers=2)}.get(aid)
espn.now_utc = lambda: NOW
espn.boxscore = lambda gid, use_cache=True: None   # no player data -> no props

import run  # noqa: E402

sys.argv = ["run.py", "--winner-file", str(FX / "winner_nba.json"), "--no-open"] + sys.argv[1:]
run.main()
