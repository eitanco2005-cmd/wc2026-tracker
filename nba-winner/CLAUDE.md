# NBA × Winner (ווינר) — betting project

Daily NBA bet recommendations against Winner (Israel's state sports-betting operator, winner.co.il), run as a bankroll
"project" with a start balance, profit target and stop-loss. Owner: Ethan. Talk to him in Hebrew, keep it short.

Site (GitHub Pages, public): https://eitanco2005-cmd.github.io/wc2026-tracker/nba-winner/ (= `nba-winner/index.html`)

## How the pieces fit

| Step | Where | What |
|---|---|---|
| 1. Projections | GitHub Actions `.github/workflows/nba-winner.yml`, daily 08:00 UTC (10:00 Israel winter: settle last night, update site) and 15:47 UTC (fresh projections before picks) + manual dispatch | `python run.py settle` grades finished bets → `python run.py` tries Winner (always 403 from GitHub) → falls back to price-sheet mode, writes `data/projections.json`, re-renders the site |
| 2. Winner odds | **Claude in Chrome** on the owner's PC (Winner blocks non-Israeli/server IPs) | run `tools/winner_capture.js` on https://www.winner.co.il/ |
| 3. Picks | this repo, locally in the session | `python run.py picks --winner-file data/winner_nba_latest.json --no-open` → logs tickets to `data/picks.csv`, renders `index.html`, commit + push → Pages deploys |

The session sandbox has **no network access to ESPN or Winner**; never try to fetch them from Bash. ESPN data only
comes from the Action; Winner odds only via Claude in Chrome. GitHub (git push, `gh`) works.

## Automatic daily picks

A Claude desktop-app scheduled task `nba-winner-daily-picks` (file `C:\Users\eitan\.claude\scheduled-tasks\nba-winner-daily-picks\SKILL.md`)
runs the `/picks` procedure below every day at 18:30 local time. It needs the PC on, the Claude app open, and Chrome open
with the extension connected; if the app was closed, it runs on next launch.

## `/picks` procedure (when Ethan says "picks")

1. `git pull --rebase`. Check `data/projections.json` → `created` is from today (Israel time). If not, run
   `gh workflow run nba-winner.yml --ref main`, wait for it (`gh run list --workflow nba-winner.yml`), pull again.
2. Claude in Chrome: `tabs_context_mcp` (createIfEmpty) → new tab → navigate `https://www.winner.co.il/` →
   `javascript_tool` with the full contents of `tools/winner_capture.js` → returns length of `window.__c`.
   - Odds MUST come from `https://api.winner.co.il/...` with `credentials:'include'` (the script does this).
     `www.winner.co.il/api/...` is a stale snapshot — never use it.
3. Read `window.__c` in slices of 1000 chars (`window.__c.slice(0,1000)`, …); longer outputs get truncated.
   Join the slices exactly, write to a text file, then:
   ```
   python3 -c "import json,sys;sys.path.insert(0,'.');from nbaw.compact import decode;m=decode(open('LINE.txt').read());json.dump({'markets':m},open('data/winner_nba_latest.json','w',encoding='utf-8'),ensure_ascii=False);print(len(m))"
   python3 run.py picks --winner-file data/winner_nba_latest.json --no-open
   ```
   Sanity: all teams decoded (no `?`), number of matched games ≈ number of NBA games tonight.
4. Commit (`nba-winner/data nba-winner/index.html nba-winner/reports`), pull --rebase, push. Wait for the
   "pages build and deployment" run to succeed. Close the Chrome tab.
5. Reply in Hebrew with a short table: game · bet in plain words · odds · stake ₪, the total stake, and any
   "קו חריג" warning. Never present a bet as a sure thing.

If the Chrome extension isn't connected: tell Ethan (Chrome must be open, extension signed in to the same account).

## Winner rules (checked 15/11/2026 on winner.co.il "כללי משחק ווינר ליין" + the UI) — enforced in `nbaw/rules.py`

- Combination (parlay): 2–10 selections. We use 2–3 (`config.PARLAY_MAX_LEGS`).
- NBA game markets are marked **SD** → allowed as single, double or more.
- No two options from the same event in one combination → max one leg per game.
- Cancelled game → odds 1 (settlement treats a push leg as 1.0).
- The board may cap max payout per ticket (amount not published). No published minimum stake found.

## Project settings — `nbaw/config.py`

`START_BALANCE`, `PROFIT_TARGET`, `STOP_LOSS_PCT`, `DAILY_MAX_EXPOSURE`, `MAX_SINGLES_PER_DAY`,
`MAX_PARLAYS_PER_DAY`, `KELLY_FRACTION`, `MAX_SINGLE_STAKE_PCT`, `MAX_SINGLE_STAKE_PCT_BY_TIER`, `MAX_PARLAY_STAKE_PCT`, `MIN_EV` per tier.
Since 17/11/2026 (Ethan delegated the call): single cap A 3% / B 2.5% / C 1.5% / P 1.5% of balance; profit target kept at 500.
Balance = START_BALANCE + sum of settled P&L in `data/picks.csv`. The ledger assumes Ethan placed exactly what the site
showed. A new `picks` run replaces pending tickets whose games haven't started; started/settled ones stand.
Project auto-stops (no new tickets) at target or at the stop-loss floor.

## Model (short)

- `nbaw/model.py`: recency-weighted ridge team ratings (this + last season from ESPN), learned home edge and
  back-to-back effect, offence/defence for totals, injury impact from ESPN injuries × player box-score value.
  Calibrates SDs and half/quarter fractions from historical line scores.
- `nbaw/engine.py`: blends with de-vigged DraftKings lines (via ESPN, `MARKET_WEIGHT`=0.7); EV per Winner outcome;
  tiers A (full game) / B (half, team total) / C (quarter); blocks games where model and market disagree a lot;
  `line_anomalies` flags Winner half/quarter lines inconsistent with Winner's own full-game line ("קו חריג").
- Winner margin is ~11–14% per two-way market; most days the honest answer is "no bet".
- `nbaw/players.py` — **player points props** ("מעל/מתחת נקודות שחקן"). The Action pulls this season's ESPN box
  scores (`espn.boxscore`, cached per game), projects each rotation player (points-per-minute × expected minutes ×
  team's projected points tonight / team average), calibrates sd = a + b·mu walk-forward, and stores
  `proj["players"]` in `projections.json`. In `picks`, Winner's Hebrew name is matched to tonight's ESPN players
  (transliteration + `config.PLAYER_NAME_SEED` + optional `data/player_names.json` overrides); unmatched → warning, skipped.
  Tier **P**, `MIN_EV["P"]`=10%, singles only (never in parlays), max `MAX_PROPS_PER_DAY`. Blocked if the player is
  on the injury report (anything but probable), projects < `PROP_MIN_MINUTES`, |model − line| > `PROP_MAX_GAP`, or the
  game total is blocked. Whole-number lines have an "exactly" outcome on Winner: over N = N+1 or more, landing on N
  loses. Did-not-play is graded as void — **assumption, Winner's rule not verified**. As of 17/11/2026 Winner lists
  player points only for Deni Avdija (one market per game).

## Files

- `run.py` — CLI: `today` (default), `picks`, `settle`, `ratings`.
- `nbaw/site.py` — the mobile Hebrew site (rendered from the ledger). `nbaw/report.py` — technical full report
  (`reports/latest_full.html`) and price sheet. `nbaw/hebrew.py` — team names + plain-Hebrew bet sentences.
- `nbaw/compact.py` + `tools/winner_capture.js` — browser capture format: `mId|HOME-AWAY|YYMMDDHHMM|<FG|H1|Q1><S|O|T<team>|P<hebrew player>>|sel:price,...;`
- `tests/offline_test.py`, `tests/offline_sheet.py` — offline end-to-end tests with fixtures (synthetic history).
- `tests/offline_props.py` — player props: decode, name matching, probabilities, grading, sheet → picks → settle.
- `data/` — `picks.csv` (ledger), `projections.json`, `meta.json`, Winner captures. Committed on purpose.

## Conventions

- Commit messages end with the session attribution lines the environment gives you.
- Don't change the project's money settings or reset `data/picks.csv` without Ethan asking.
- Repo is public → everything in `data/` and the site is public.
