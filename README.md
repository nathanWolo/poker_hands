# Rush Tracker

Local PokerTracker-style analyzer for **GGPoker** cash hand histories (Rush & Cash NLHE, plus PLO).

## Run

```bat
python -m pip install -r requirements.txt
python app.py
```

Or double-click `start.bat`. The app opens at [http://127.0.0.1:5050](http://127.0.0.1:5050) and imports the zips in `data/imports` on first launch.

## What it shows

- HUD stats: VPIP, PFR, 3-bet, fold to 3-bet, steal, BB vs steal, c-bet, WTSD, W$SD, aggression
- Session list (new session after a 20-minute gap)
- Filterable hand list with a street-by-street replayer
- Position / hour / day reports and a leak finder vs typical 6-max cash frequencies
- 13×13 starting-hand matrix colored by BB/100
- Opponent HUD for hashed Rush player IDs
- Cumulative and daily graphs

Drop additional GGPoker `.zip` or `.txt` exports on the Import page.

## GTO solver

[TexasSolver](https://github.com/bupticybee/TexasSolver) (Windows v0.2.0) is installed under `tools/texassolver/bin`. The tracker calls `console_solver.exe` — it is **heads-up postflop Hold'em only**.

- Open **Solver** in the app, or click **Solve this spot** in the replayer on a HU flop/turn/river
- Re-download: `python tools/setup_texassolver.py`
- Standalone GUI: `tools/texassolver/bin/TexasSolverGui.exe`

TexasSolver is AGPL-3.0. This project invokes the official binary and does not copy its source.
