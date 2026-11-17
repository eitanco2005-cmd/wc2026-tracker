"""Tunable settings. Edit freely."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

TZ = "Asia/Jerusalem"

# ---- Bankroll / staking -------------------------------------------------
BANKROLL = 1000.0          # ₪ — your total betting bankroll
KELLY_FRACTION = 0.25      # quarter-Kelly
MAX_SINGLE_STAKE_PCT = 0.03   # raised from 2% at owner request (17/11/2026)
MAX_PARLAY_STAKE_PCT = 0.01
MIN_STAKE = 5.0            # Winner minimum-ish; stakes below this are rounded up/shown as minimum

# ---- Which bets qualify -------------------------------------------------
# Minimum expected value (EV) per confidence tier.
#   A = full-game spread/total/ML anchored to the sharp market
#   B = team totals / 1st-half markets (derived from the market)
#   C = 1st-quarter markets (derived, noisiest)
#   P = player points props (own model only — no sharp market to anchor to)
MIN_EV = {"A": 0.02, "B": 0.04, "C": 0.06, "P": 0.10}

# ---- Player points props -------------------------------------------------
PROP_MIN_GAMES = 6           # games played this season before we price a player
PROP_MIN_MINUTES = 22        # projected minutes; bench players are too volatile
PROP_HALF_LIFE_DAYS = 30     # recency weighting of scoring rate
PROP_MIN_HALF_LIFE_DAYS = 10 # recency weighting of minutes (role changes fast)
PROP_MAX_GAP = 6.0           # |model - Winner line| above this -> assume Winner knows something
PROP_OK_STATUS = ("", "probable")  # injury report status allowed for a prop bet
MAX_PROPS_PER_DAY = 1
PROP_DEFAULT_CAL = {"a": 2.5, "b": 0.25, "bias": 1.0}   # sd = a + b*mu until calibrated
# Winner (Hebrew) -> ESPN display name, for names the automatic matcher can't be trusted with.
# More can be added in data/player_names.json ({"<hebrew>": "<ESPN name or athlete id>"}).
PLAYER_NAME_SEED = {"דני אבדיה": "Deni Avdija"}

# ---- Parlays ------------------------------------------------------------
PARLAY_MAX_LEGS = 3
PARLAY_MIN_LEGS = 2
PARLAY_MIN_PROB = 0.12     # don't suggest lottery tickets
PARLAY_TOP_N = 5
PARLAY_POOL = 12           # best N legs considered

# ---- Model --------------------------------------------------------------
MARKET_WEIGHT = 0.70       # weight on sharp market vs. own model when both exist
HALF_LIFE_DAYS = 40        # recency weighting of current-season games
PRIOR_SEASON_WEIGHT = 0.15 # weight of every last-season game (prior)
RIDGE_LAMBDA = 4.0
# If the model disagrees with the sharp market by more than this, assume the market
# knows something (injury/rest news) and don't recommend that game's spread/total.
MAX_MODEL_GAP_MARGIN = 7.0
MAX_MODEL_GAP_TOTAL = 12.0

# Fallback distribution parameters (overwritten by calibration from history)
DEFAULT_SD = {
    "FG_margin": 12.8, "FG_total": 18.5, "team_pts": 11.5,
    "H1_margin": 8.6, "H1_total": 12.0,
    "Q1_margin": 5.9, "Q1_total": 7.6,
}
DEFAULT_FRAC = {"H1_margin": 0.48, "H1_total": 0.505, "Q1_margin": 0.24, "Q1_total": 0.255}

# Injury status → probability the player sits
INJURY_WEIGHT = {"out": 1.0, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.3, "probable": 0.1}
INJURY_TEAM_CAP = 12.0     # max points of impact per team

HTTP_TIMEOUT = 20

# ---- The project ---------------------------------------------------------
PROJECT_NAME = "פרויקט NBA בווינר"
PROJECT_START_DATE = "2026-11-15"
START_BALANCE = 1000.0      # ₪ starting bankroll
PROFIT_TARGET = 500.0       # ₪ profit goal -> stop when balance reaches START + TARGET
STOP_LOSS_PCT = 0.40        # stop the project if balance falls 40% below start
DAILY_MAX_EXPOSURE = 0.10   # never put more than 10% of balance on one day
MAX_SINGLES_PER_DAY = 4
MAX_PARLAYS_PER_DAY = 1
