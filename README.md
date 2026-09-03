# Rush Tracker

Rush Tracker is a **local** PokerTracker-style app for **GGPoker cash** hand histories. It is built for **Rush & Cash No-Limit Hold'em**, and it also imports **PLO** cash hands. Everything runs on your machine: a Flask server, a SQLite database, and a browser UI at [http://127.0.0.1:5050](http://127.0.0.1:5050).

It is **not** a real-time HUD overlay, not an online database, and not a multiway / preflop GTO solver. Hand histories stay on disk under `data/`. Nothing is uploaded unless you push the **source** to GitHub yourself — the tracker never talks to GGPoker after you import files.

---

## Table of contents

1. [What you can do with it](#what-you-can-do-with-it)
2. [What it does not do](#what-it-does-not-do)
3. [Requirements](#requirements)
4. [Install and first launch](#install-and-first-launch)
5. [Exporting hands from GGPoker](#exporting-hands-from-ggpoker)
6. [How import works](#how-import-works)
7. [The filter bar (applies to almost every page)](#the-filter-bar-applies-to-almost-every-page)
8. [Page-by-page guide](#page-by-page-guide)
   - [Overview](#overview)
   - [Sessions](#sessions)
   - [Hands and the replayer](#hands-and-the-replayer)
   - [Reports](#reports)
   - [Starting hands](#starting-hands)
   - [Players](#players)
   - [Graphs](#graphs)
   - [Solver](#solver)
   - [Import](#import)
9. [HUD stat glossary](#hud-stat-glossary)
10. [Frequency leak finder (vs 6-max cash)](#frequency-leak-finder-vs-6-max-cash)
11. [GTO leak analysis (TexasSolver)](#gto-leak-analysis-texassolver)
12. [Where files live](#where-files-live)
13. [Running tests](#running-tests)
14. [Troubleshooting](#troubleshooting)

---

## What you can do with it

- Import GGPoker `.zip` or `.txt` cash histories (NLHE and PLO).
- See **net won**, **BB/100 before and after rake**, won/lost counts, and rake paid from pots you collected.
- Read a full **HUD**: VPIP, PFR, 3-bet, fold to 3-bet, steal, fold vs steal, flop c-bet, fold to c-bet, WTSD, W$SD, W$WSF, aggression factor.
- Split play into **sessions** (a new session starts after a **20-minute** gap).
- Browse every hand, search by hand ID / cards / board, and **replay** it street by street on a 6-max table.
- Break results down by **position**, **hour of day**, and **calendar day**.
- Open a **13×13 starting-hand matrix** colored by BB/100, then jump into those hands.
- Look at **opponent HUD** stats (Rush uses hashed IDs, so regulars rarely repeat).
- Plot **cumulative $** (before vs after rake) and **daily net**.
- Flag frequencies that sit outside typical **6-max cash** ranges.
- On heads-up Hold'em flops/turns/rivers, run **TexasSolver** and compare your line to a GTO mix.

---

## What it does not do

- **No live tables.** Import after you play (or after GGPoker emails / lets you download histories).
- **No PokerStars / Party / WPN** parsers. The text format must look like GGNetwork / PokerStars-style `Poker Hand #…`.
- **No tournaments / spin & gold / sit & go.** Cash only.
- **TexasSolver is Hold'em, heads-up, postflop only.** It will not solve preflop, 3-way pots, or PLO.
- **GTO “EV lost” is a frequency heuristic**, not true chip EV from the solver. See [GTO leak analysis](#gto-leak-analysis-texassolver).
- The server binds to **127.0.0.1 only**. Other devices on your network cannot open it unless you change the code.
- Graphs load **Chart.js from a CDN**. The rest of the app works offline; the charts need internet the first time (or a cached copy).

---

## Requirements

| Piece | Detail |
| --- | --- |
| OS | Windows is the fully supported path (solver binary + `start.bat`). The Flask tracker can run on macOS/Linux; TexasSolver setup here is the official **Windows** zip. |
| Python | **3.10+** (the code uses modern type syntax). |
| Packages | `flask==3.1.1` (app) and `pytest==8.4.1` (tests). See `requirements.txt`. |
| Browser | Any current Chromium/Firefox/Edge. The UI is a single page with hash routes (`#/overview`, `#/hands`, …). |
| Disk | SQLite file `data/poker.db` grows with your history. Solver dumps go under `data/solver/` and can be large. |
| Optional | [TexasSolver v0.2.0 Windows](https://github.com/bupticybee/TexasSolver/releases) for GTO. AGPL-3.0; this project **calls the official binary** and does not vendor TexasSolver source. |

---

## Install and first launch

### Option A — double-click

1. Unzip or clone this folder somewhere you can write files (not a read-only USB stick).
2. Double-click `start.bat`.
3. It runs `python -m pip install -r requirements.txt`, then `python app.py`.
4. After about a second, your browser should open [http://127.0.0.1:5050](http://127.0.0.1:5050).

Leave the black console window open while you use the tracker. Closing it stops the server. Press a key in that window only after you have quit the app (the script `pause`s on exit).

### Option B — terminal

From the project root:

```bat
python -m pip install -r requirements.txt
python app.py
```

You should see something like:

```text
No database yet — importing GGPoker zips from data/imports ...
Imported 0 hands from 0 files (0 sessions).
Tracker running at http://127.0.0.1:5050
```

or, on later launches:

```text
Loaded existing database with 12345 hands.
Tracker running at http://127.0.0.1:5050
```

If port **5050** is already in use, the process will fail. Close the other copy of Rush Tracker (or whatever is on 5050) and try again.

### First-run import

On boot, if `data/poker.db` has **zero hands**, the app automatically imports:

1. Every `*.zip` in `data/imports/`, if that folder has zips, **or**
2. Every `*.txt` under `data/raw/` if there are no zips.

Put your GGPoker export zips in `data/imports/` **before** the first launch if you want them loaded immediately. Otherwise start the app empty and use the **Import** page.

---

## Exporting hands from GGPoker

GGPoker / GGNetwork typically emails or lets you download a **zip of `.txt` files** for cash / Rush & Cash. The tracker expects PokerStars-style text that starts with:

```text
Poker Hand #XXXX: Hold'em No Limit ($0.05/$0.10) - 2026/01/15 12:34:56
```

or Omaha:

```text
Poker Hand #XXXX: Omaha Pot Limit ($0.05/$0.10) - ...
```

**Hero** must be named `Hero` in the seat list (GGPoker’s default for “your” player). The parser marks that seat as you. If the file uses a screen name instead of `Hero`, stats will not attach to you correctly.

Practical tips:

- Download overlapping date ranges freely. Hands are **de-duplicated by hand ID**; re-importing the same hand is a skip, not a double count.
- Keep the original zip. The tracker copies text into SQLite; it does not need the zip after a successful import, but a rebuild reads `data/imports` again.
- One upload in the browser can be up to **80 MB**. For huge archives, drop the zip into `data/imports/` and click **Rebuild from bundled zips**, or split the download.

---

## How import works

| You do this | What happens |
| --- | --- |
| Drop `.zip` / `.txt` on **Import** | Files are saved to a temp folder, parsed, inserted, then discarded. |
| Empty POST / first boot | Reads `data/imports/*.zip`, else `data/raw/**/*.txt`. |
| **Rebuild from bundled zips** | **Deletes the database**, then re-imports from `data/imports` (or `data/raw`). GTO reviews and solver cache go away too. |

A zip is scanned for nested `.txt` files only (other members are ignored). Encoding is tried in order: UTF-8 with BOM, UTF-8, UTF-16, Windows-1252.

After a successful insert, **sessions are rebuilt** from timestamps (20-minute gap).

Import result language in the UI:

- *Nothing imported* — no new text found.
- *All N hands were already in the database* — duplicates only.
- *Parsed … added … skipped … duplicates* — mixed new + old.

Supported hand features in the parser: NLHE, PLO, **run it twice/thrice**, **EV cashout** (risk + receive), **cash drop**, GGPoker extra pot lines (rake, jackpot, bingo, fortune, tax).

---

## The filter bar (applies to almost every page)

The bar at the top is **global**. Changing it and clicking **Apply** reloads Overview, Sessions, Hands, Reports, Matrix, Players, Graphs, and the solver leak catalog using the same slice of the database.

| Control | Behavior |
| --- | --- |
| **Game** | `NL Hold'em` (default), `PLO`, or `All games`. Defaulting to NLHE is intentional: Rush volume is Hold'em, and the solver is Hold'em-only. Switch to PLO or All if you imported Omaha. |
| **Position** | Hero seat: UTG, HJ, CO, BTN, SB, BB. Empty = all. 7-max+ labels like UTG+1 exist in the parser but are not in this dropdown — use Search or leave Position on All. |
| **Result** | All / Won (`hero_net > 0`) / Lost (`hero_net < 0`). |
| **From / To** | Inclusive calendar dates on `played_at` (To is end of that day, 23:59:59). |
| **Search** | Substring match on hand ID, hero cards, board, or the **raw** history text (player IDs, table names, etc.). |
| **Reset** | Clears dates/search/position/result and sets Game back to **NLHE**. |

The starting-hand matrix can also set a hidden `hand=AKs` filter (see [Starting hands](#starting-hands)).

**Apply** is required after you change fields; the form does not auto-submit on every keystroke.

---

## Page-by-page guide

Left sidebar: Overview, Sessions, Hands, Reports, Starting hands, Players, Graphs, Solver, Import. The footer of the sidebar shows **hand count** and the first→last timestamp of the current filter (on Overview).

### Overview

Start here after each import.

**KPI row**

- **Net won** — sum of Hero’s result in dollars (after rake already taken from the pot in the history). Green = up, red = down.
- **BB / 100** — two numbers:
  - **before rake**: `(net + your share of fees) / big blinds put in play × 100`
  - **after rake**: `net / big blinds × 100`  
  “Your share of fees” is rake + jackpot + bingo + fortune + tax, allocated only on pots **you collected**, proportional to how much of the distributed pot you took.
- **Won / lost** — count of hands with positive vs negative net (chops/even are neither).
- **Rake paid** — dollar total of that fee share (from pots you won).

**HUD strip** — see [HUD stat glossary](#hud-stat-glossary). Percentages that have no opportunity (denominator 0) show as **—**.

**Cumulative winnings chart** — hand index on X, dollars on Y. Blue line = before rake, green/red filled line = after rake. Note under the chart repeats gross / net / rake paid.

**Leak finder vs 6-max cash** — each row is a frequency vs a target band. Status **in range**, **low**, or **high**. This is **not** GTO; it is a coaching-style 6-max cash template. If you have already run TexasSolver analysis, a **GTO mismatch (sample)** row appears with a dollar figure and a link to Solver.

**Biggest wins / losses** — eight best and eight worst hands in the current filter. Click a row to open that hand in the replayer (`#/hands/<id>`).

### Sessions

One row per sitting. A sitting **ends** when the next hand is more than **20 minutes** after the previous hand (by history timestamp, not wall clock).

Columns: start, end, duration (minutes), hands, VPIP, PFR, BB/100, **$/hr** (net ÷ hours; **—** if duration is 0), net.

Use this to find tilt sessions, dead hours, or a single monstrous sitting. Filters still apply (e.g. only BB, only last month).

### Hands and the replayer

**Left:** paginated table (40 hands per page), newest first. Columns: time, position, hole cards, board, pot, net. Click a row to load the replayer on the right.

**Search** is the fastest way to jump to a specific `Poker Hand #`.

**Replayer (right panel)**

- Hero is always the bottom seat; others rotate around the felt.
- **Prev / Next / End** step through blinds, posts, folds, checks, calls, bets, raises, uncalled bets, collections, and shows.
- The board reveals by street (nothing preflop, 3 flop, 4 turn, 5 river). Run-it-twice extra boards are in the raw history; the felt uses the primary board.
- Opponent hole cards stay face-down until a **show** (or showdown), unless they folded.
- The **pot** on the felt is the sum of money put in so far in the replay (not always identical to the summary “Total pot” line).
- **Solve this spot** jumps to `#/solver/<hand-id>` and pre-fills board, pot (cents), stacks, hero cards, and IP/OOP if the hand is HU postflop NLHE.
- Expand **Raw history** to read the original text.

If a GTO review exists for this hand (you ran leak analysis), the replayer **seeks to your decision**. The Next button becomes **Take action**: first you see action *before* your choice; pressing it plays your line and reveals the solver mix. See [Reviewing a scored hand](#reviewing-a-scored-hand-in-the-replayer).

### Reports

**By position** — UTG through BB: hands, VPIP, PFR, 3-bet, steal, WTSD, BB/100, net. Steal is only meaningful for CO/BTN/SB (those are the steal seats). BB fold-vs-steal lives on Overview / the leak list, not this table.

**By hour** — `00:00`–`23:00` from the timestamp in the history (GGPoker’s clock, usually your client’s timezone as written in the file).

**By day** — calendar date, hands, BB/100, net.

Use filters to isolate “Sunday nights on the button” etc. Combine **From/To** + **Position**.

### Starting hands

A 13×13 grid:

- **Diagonal** = pairs (`AA` … `22`)
- **Upper triangle** = suited (`AKs`)
- **Lower triangle** = offsuit (`AKo`)

Color is **BB/100** for that combo in the current filter (green profitable, red not). The small number is **sample size**. Empty dark cells mean you never played that combo in the filter.

**Click a cell** to open Hands filtered to that starting hand (`hand=AKs`). Reset filters (or change Game/dates) when you want the full pool again.

### Players

Opponents with **5 or more** hands against you in the current filter (50 per page of the API; the page shows that first slice). Columns: name, hands, VPIP, PFR, 3-bet, flop c-bet, WTSD, W$SD.

On **Rush & Cash**, names are usually hashed IDs. They rarely persist, so this page is more useful on **regular cash** tables than on Rush. Do not treat a 7-hand sample as a real read.

### Graphs

- **Cumulative $** — same equity curve as Overview (before vs after rake).
- **Daily net** — bar chart, green up-days / red down-days.

If the canvases are empty, Chart.js failed to load (no network). Stats tables elsewhere still work.

### Solver

Two tools on one page: **batch leak analysis** (top) and a **manual solve form** (bottom). Requires `tools/texassolver/bin/console_solver.exe`. If the headline says **binary not found**, run:

```bat
python tools/setup_texassolver.py
```

That downloads TexasSolver **v0.2.0 Windows** into `tools/texassolver/bin`. You can also open the vendor GUI with **Open TexasSolver GUI** (`TexasSolverGui.exe`).

Full GTO workflow is in [GTO leak analysis](#gto-leak-analysis-texassolver).

### Import

- Drag-and-drop or file picker: `.zip` and `.txt`, multiple files allowed.
- **Import selected** — add to the existing database (skip duplicates).
- **Rebuild from bundled zips** — wipe SQLite and re-read `data/imports`. Confirm you mean it; this is the nuclear option.

The note on the page is accurate: overlapping downloads are safe; NLHE, PLO, run-it-twice, EV cashout, and cash drops parse.

---

## HUD stat glossary

All percentages are `100 × successes / opportunities` unless noted. Opportunities are counted from **Hero’s** flags unless you are on the Players page (then it is that opponent’s flags in hands vs you).

| Stat | Meaning in this tracker |
| --- | --- |
| **VPIP** | Voluntarily put money in preflop (call or raise, not blinds). |
| **PFR** | Preflop raise (open or 3-bet, etc., as tagged by the parser). |
| **3-bet** | Hero 3-bets / hands where Hero had a 3-bet opportunity. |
| **Fold to 3-bet** | Hero folds to a 3-bet / times Hero faced a 3-bet after opening. |
| **Steal** | Hero opens from **CO, BTN, or SB** when it is a steal opportunity / those opportunities. |
| **Fold vs steal** | Hero (typically BB) folds to a steal / times Hero faced a steal. |
| **C-bet flop** | Hero continuation-bets the flop as preflop aggressor / flop c-bet opportunities. |
| **Fold to c-bet** | Hero folds to a flop c-bet / times Hero faced one. |
| **WTSD** | Went to showdown / hands where Hero saw a flop. |
| **W$SD** | Won money at showdown / hands that went to showdown. |
| **W$WSF** | Won money when seeing flop / saw flop. |
| **AF** | Aggression factor: `(bets + raises) / calls` on flop+turn+river. If there are zero calls, AF is just `bets+raises` or **—**. |

**BB/100** uses the sum of big-blind sizes of the filtered hands as the denominator, so mixed stakes still produce one number.

**Net** is Hero collected − Hero invested, in dollars, including uncalled bets returned, cashout receive, minus cashout risk, as parsed from the history.

---

## Frequency leak finder (vs 6-max cash)

Overview (and internally the same list on Reports’ data) compares your HUD to **broad 6-max cash** bands. These are coaching defaults, not GGPoker Rush-specific and not GTO.

| Stat | Target | If **low** | If **high** |
| --- | --- | --- | --- |
| VPIP | 22–28% | Too tight | Too loose |
| PFR | 18–24% | Not raising enough when entering | Opening too wide |
| VPIP−PFR gap | 3–8 percentage points | Almost never calling (raise-or-fold) | Too much calling |
| 3-bet | 7–11% | 3-bet range too small | 3-betting too wide |
| Fold to 3-bet | 45–62% | Calling/4-betting too often | Overfolding |
| Steal | 32–45% | Not opening enough CO/BTN/SB | Opening too wide when folded to |
| Fold BB vs steal | 68–82% | Defending blinds too wide | Folding too much vs steals |
| C-bet flop | 50–70% | Giving up too often | Barreling too thin |
| Fold to flop c-bet | 38–55% | Calling station | Overfolding |
| WTSD | 24–32% | Giving up too much after flop | Going to showdown too often |
| W$SD | 50–56% | Showing down too weak | Winning showdowns a lot (can be tight or lucky) |
| Aggression factor | 2.2–3.6× | Too passive postflop | Too aggressive postflop |

Rows **out of range** sort to the top. Small samples make this noisy — filter to 5k+ NLHE hands before treating a “high VPIP” as a real leak.

---

## GTO leak analysis (TexasSolver)

### What gets solved

A hand is **eligible** when all of these hold:

- Game type is **NLHE** (PLO is skipped).
- Hero **saw a flop**.
- At the first postflop street that is still **heads-up**, TexasSolver can build a spot: 3/4/5 board cards, pot and effective stack in **cents** (chip units), OOP = first to act, IP = the other player.

Preflop folds, 3-way flops, and limped multiway pots never enter the catalog.

Villain’s range is **not** read from the hand. The solver uses TexasSolver’s **default 6-max cash IP/OOP ranges** (from the binary’s parameter file if present, else a built-in approximation). Treat results as “vs a generic strong 6-max range,” not vs that Rush whale.

Bet sizes on the tree are a fixed template (about 50% pot bets, 60% raises, all-in, river 60/100 raises, OOP river donk 50%). **Your real sizing may not exist on the tree.** The UI will say *Your sizing is off the solver tree* and score that as a leak against the solver’s top action.

### Presets (quality vs time)

| Preset | Accuracy | Max iterations | Typical timeout | Used for |
| --- | --- | --- | --- | --- |
| **quick** | 8.0 | 8 | 30s | Full-database scan (“All eligible”) |
| **audit** | 5.0 | 12 | 60s | Default leak sample |
| **fast** | 2.0 | 40 | 90s | Manual form default |
| **normal** | 1.0 | 100 | 180s | Manual deeper solve |
| **quality** | 0.5 | 200 | 300s | Manual slow solve |

These are coarse on purpose so the UI stays usable. They are **not** Pio-level precision.

### Batch: “Analyze biggest leaks”

On **Solver**:

1. Confirm the filter bar (usually NLHE, maybe a date range). The catalog counts eligible HU spots **in that filter**.
2. **Sample**: 8, 12 (default), 20 spots, or **All eligible (~30s each)**.
3. **Pick**: biggest **losses** first, or biggest **pots** first.
4. **Quality**: Audit for a sample; choosing “All eligible” forces **quick**.
5. Click **Analyze biggest leaks**. Only one job can run at a time. Progress polls every 3 seconds; you can stay on the page.

Sample sizes 8/12/20 are capped at 40 internally. **All** walks every eligible HU spot and can take many hours on a large database (about 30 seconds each on **quick**, and repeats are cached by board+pot+stack+preset).

When finished you get:

- **Estimated mismatch $** — sum of per-spot leak scores (see formula below).
- Breakdowns **by street**, **IP vs OOP**, **action type**, **hero position**.
- **Worst mismatches** table: your action, solver’s preferred action, GTO frequency of *your* action, estimated leak, realized net.

### What “est. leak” means

TexasSolver dumps **action frequencies**, not chip EVs. The tracker scores:

```text
est. leak ($) = (GTO frequency of best action − GTO frequency of your action) × pot
```

- Taking the solver’s top action → **$0** leak for that spot.
- A 0% GTO line → leak ≈ **full pot × best-action frequency** (often ≈ pot if the solver is nearly pure).
- Combo **not in the default range** → leak **$0** and a note *Hero combo is not in the default GTO range.*
- Unmatched sizing → leak uses best-action frequency × pot, with a sizing note.

This ranks **disagreement with a default tree**, not “you lost this many big blinds in expectation.”

### Reviewing a scored hand in the replayer

Click a row in **Worst mismatches** (or open the same hand under Hands):

1. The felt shows **all action before your scored decision**.
2. Press **Take action** to play your real line.
3. A **GTO policy** panel shows mix bars for **your combo**: your action vs the solver’s favorite, with percentages.

From Hands, **Solve this spot** still opens the manual form if you want to edit ranges and re-solve.

### Manual solve form

Fields (pot and stack are **cents**: $0.50 pot = `50` if BB is in dollars with 2 decimals stored as cents — a $5 pot is `500`):

- **Board** — comma-separated, e.g. `Qs,Jh,2h` (flop), add turn/river cards for later streets.
- **Pot (cents)** / **Effective stack (cents)**
- **Hero cards** — e.g. `Ah Kd` (optional; used to highlight your combo in the mix)
- **Hero role** — OOP or IP
- **Quality** — fast / normal / quality
- **IP range / OOP range** — TexasSolver range strings. **Leave blank** to use defaults.

**Solve** blocks the tab until done (can be a minute+). Output:

- Mix for **first to act** (OOP)
- Mix **after check** (IP), if dumped
- Average range mix and, if your combo is in range, **your hand** mix
- Collapsible solver log

Opening `#/solver/<hand-id>` (from the replayer) pre-fills these from the first HU postflop street.

---

## Where files live

```text
poker_hands/
  app.py                 # Flask app, port 5050
  start.bat              # Windows launcher
  requirements.txt
  engine/                # parser, stats, importer, solver wrapper, GTO scoring
  static/                # UI (index.html, css, js)
  tests/                 # pytest
  tools/
    setup_texassolver.py # download official Windows binary
    texassolver/bin/     # console_solver.exe, GUI, resources (not in git)
  data/
    poker.db             # your hands, sessions, GTO cache (not in git)
    imports/             # drop zips here for boot/rebuild
    raw/                 # optional loose .txt trees
    solver/              # last_result.json and solver working files
```

`.gitignore` keeps **hands and binaries** out of git: `data/raw/`, `data/imports/*` (except `.gitkeep`), `data/*.db*`, `data/solver/`, `tools/texassolver/bin/`.

---

## Running tests

From the project root (after `pip install -r requirements.txt`):

```bat
python -m pytest
```

Tests use **synthetic** hand histories in `tests/hh.py`, not your GGPoker files. Solver tests skip or stub if the binary is missing.

---

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Browser does not open | Go to [http://127.0.0.1:5050](http://127.0.0.1:5050) yourself. Confirm the console says `Tracker running`. |
| `Address already in use` | Another `python app.py` is running. Close that console. |
| Empty Overview / 0 hands | Game filter is **NLHE** by default. Switch to **PLO** or **All** if you only imported Omaha. Or import files on the Import page. |
| Import does nothing | Files must be `.zip` containing `.txt`, or raw `.txt` starting with `Poker Hand #`. Max **80 MB** per browser upload. |
| Duplicate-looking results | Same hand ID cannot insert twice. If nets look doubled, you probably rebuilt then also imported the same zip another way — check hand count vs GGPoker’s count. |
| Stats look like they belong to villains | Histories must label you as **Hero**. |
| Solver button disabled / “binary not found” | `python tools/setup_texassolver.py`. Windows only for the official zip this script fetches. |
| “Need a heads-up flop, turn, or river” | You tried to solve a 3-way pot or a preflop-only hand. |
| “Could not load this view” on Graphs | Chart.js CDN blocked; other pages still work. |
| Rebuild “lost” GTO reviews | Expected: rebuild wipes `poker.db`. |
| Analysis already running | Wait for the progress bar to finish, or restart `app.py` to kill the background thread. |

For parser edge cases, open the hand, expand **Raw history**, and confirm the text is standard GGPoker cash format. If you change Python files, restart `app.py` — it does not auto-reload (`debug=False`).
