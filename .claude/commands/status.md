---
description: Project status — balance, target progress, W/L, open bets (Hebrew)
---
In `nba-winner/`: `git pull --rebase`, then run
`python3 -c "import sys;sys.path.insert(0,'.');from nbaw import tracker,project;import json;print(json.dumps(project.state(tracker.load()),ensure_ascii=False,indent=1,default=str))"`
and answer in short Hebrew: balance vs start/target/floor, progress %, wins/losses, open bets, last few results.
