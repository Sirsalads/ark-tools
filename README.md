# A.N.S Tools

Autoclicker with an automatic inventory-cleanup routine for ARK: Survival
Ascended. It farms on its own and, every so often, opens the inventory, filters
the junk by keyword and drops it — then goes right back to swinging.

Shares its visual language with **A.N.S Watcher**: petrol-to-black canvas, cyan
glows, glass cards, and the tribe brand melting out of the backdrop.

![Dashboard](docs/dashboard.png)

Swap the backdrop by dropping your own `brand.png` (or `.gif`, `.jpg`) into
`assets/`. No file, no problem — the gradient stands on its own.

## Install

Windows, Python 3.10+.

```bash
pip install -r requirements.txt
```

Run it:

```bash
python main.py
```

Or double-click `run.bat`.

## Setting the two points

The routine only needs two clicks, but they depend on your resolution and on
what the HUD is showing. Instead of a countdown, the macro **freezes the
screen** and lets you pick them with a magnifier:

![Point picker](docs/picker.png)

1. Open the inventory in ARK — *exactly* the state the macro will use
   (inventory alone with `I`, or with a storage box open; the icon row sits in
   a different place in each).
2. Press `F9`. The window hides, the screen is captured and the overlay comes
   up.
3. Click the **search field**, then the **Drop All** button — the second icon
   of the row, right next to the crossed arrows that mean *transfer all*.
   Arrow keys nudge one pixel, `Shift`+arrow ten, `Enter` confirms, `Esc`
   cancels.
4. Each captured point keeps a zoomed thumbnail of what you targeted, and
   **Test** moves the cursor there without clicking so you can double-check.

Run the game in **borderless or windowed** mode — exclusive fullscreen cannot
be captured or overlaid.

No screenshot possible? **Estimate points for this resolution** computes a
starting guess. ARK anchors its HUD to the centre of the screen and scales it
with height, so the maths also holds on ultrawide: at 1920x1080 it gives filter
`(277, 193)` and Drop All `(457, 193)`. If you later change resolution, the
saved points are rescaled automatically on the next start.

## Updating

**Settings → Updates → Check for updates → Update and restart.** The app
fast-forwards its own clone (`git pull --ff-only`) and relaunches itself, so
whatever we push here lands on your machine with one click.

- `config.json`, `state/` and `captures/` are gitignored — an update never
  touches your settings, captured points or dry-run screenshots.
- It refuses to pull over uncommitted changes instead of stashing them. Commit
  or discard first.
- If `requirements.txt` changed, the card says so — run the pip install again.
- It checks once on startup (toggle in the same card). When something is
  waiting, an *update available* pill appears in the title bar.
- Rolling back is plain git: `git reset --hard <sha>`, or `git reflog` to find
  where you were.

## Templates

The drop cycle is built from **checkable templates** — a friendly name plus the
keyword that gets typed into the filter:

![Templates](docs/templates.png)

- **Add** creates one from the two fields; **Save** applies edits to the
  selected row.
- Only checked rows run, in list order (`↑` `↓` to reorder).
- **Presets…** opens a library of ARK resources grouped by what you are
  farming.

## How ARK's filter works — read this before arming

The inventory search is a case-insensitive **"contains" match on the item's
display name**, and **Drop All acts on whatever the filter left on screen**.
That is exactly what the routine exploits ([official discussion][filter]:
*"you can type 'meat' into the search and press Drop All, and only the meat
will be dropped"*).

The dangerous consequence: a short keyword also catches your gear.

| Keyword | Also lists | Risk |
|---|---|---|
| `stone` | Stone Pick, Stone Hatchet | **high** — drops your tools |
| `wood` | Wooden Club, wooden structures | **high** |
| `hide` | Hide Shirt, Hide Pants (armor) | **high** |
| `berry` | Mejoberry, Narcoberry | **high** — loses kibble and narcotics |
| `thatch`, `fiber`, `flint`, `keratin`, `chitin`, `pelt` | — | ok |
| `raw meat` | does *not* match Raw Prime Meat | ok |

Ways around it:

- Farming stone or metal? Carry **metal tools** — then `stone` is safe.
- Want only the dye berries? Use `amarberry`, `azulberry` and `tintoberry`
  instead of `berry`, so Mejoberry and Narcoberry stay in your bag.
- **Do a dry run first.**

One known gotcha: when the game's language and the system's disagree, the
search and the bulk action can work on different strings and Drop All does
nothing ([report][language]). Write the keywords in the language the game is
running in.

## Dry run

Runs the whole cycle — opens the inventory, clicks the magnifier, types the
keyword — but **never clicks Drop All**. It saves a screenshot of the filtered
inventory to `captures/` instead, so you can confirm that `stone` is not
listing your pick before letting the macro loose.

## Global hotkeys

| Key | Action |
|-----|--------|
| `F6` | start / stop the macro |
| `F7` | run a drop pass now |
| `F8` | emergency stop |
| `F9` | freeze the screen and pick the points |

All rebindable on the **Settings** tab.

## One drop pass, step by step

Fired on a click count (**14 clicks and at least 20 s of farming** by default),
on a timer, or by `F7`:

1. pause the autoclick and press the inventory key (`I` by default);
2. click the filter field and wipe the previous text with backspaces;
3. type the template's keyword;
4. click **Drop All**;
5. repeat for every checked template, in list order;
6. clear the filter, press **`Esc` twice** to close the inventory, resume
   farming.

Two presses, not one, and that is the whole trick: typing in the filter leaves
the **search field holding the keyboard**, so the first `Esc` only steps out of
the field and the second is what actually closes the panel. With a single press
the inventory stayed open and the macro kept clicking inside it — swings that
never landed on a node, and a next pass that pressed `I` into an already open
panel. Set it under **Templates → Inventory and timings → Presses to close**
(1–5). Closing with the inventory key instead takes a single press; a second
one just opens it again, so the field follows the key you pick.

After the last press the macro keeps its hands off for **two seconds**
(*Wait after closing*) — the panel has to be gone before the next swing, or
that swing lands in the inventory and the whole thing starts over.

## Clicks are not swings

The click trigger counts clicks, and clicks are free: a dino with its own
attack cooldown eats fourteen of them in two seconds and lands three hits.
So the pass waits for **both** conditions — the click count **and** a minimum
stretch of farming, 20 s by default (**Templates → When it runs → Farm for at
least**). Raise it for a slow attack animation, drop it to zero to go back to
counting clicks alone.

## GeForce NOW

**Settings → Where ARK runs → GeForce NOW.**

The client forwards your real mouse and keyboard to the server, so foreground
input works exactly as it does on an installed game — just one round trip
later. Switching the profile does three things:

- retargets the window title to the client (`GeForce NOW`);
- adds a **250 ms stream latency** allowance to every wait in the drop routine,
  so the cycle stops racing the video feed. Raise it if your connection is
  worse; your own edits to the title or the latency are never overwritten;
- measures the **video inside the window** instead of the window. The HUD is
  anchored to the picture, so with black bars an estimate based on the window
  would land half a bar off.

**Recapture your points after switching** — and note that background delivery
cannot work through the stream at all: the client captures real input, and
posted messages never reach it. The app says so if you pick it anyway.

## Anti-AFK

**Settings → Anti-AFK.** Taps one key on a timer so a cloud session is not
dropped for inactivity.

- The default key is **F15**. F13–F24 exist in the keyboard protocol but not on
  real keyboards, so ARK has nothing bound to them and the tick cannot touch
  the game.
- It ticks only while the target window has focus, and never during a drop pass
  or while you are picking points.
- While the macro is farming there is already plenty of input — this covers the
  gaps: paused, waiting for focus, or stopped with the session still open.
- If the game is not in front it stays quiet. Typing into whatever you are
  actually doing would be rude, and the stream would not see it anyway.

## Foreground vs background

| Mode | How it sends | Notes |
|------|--------------|-------|
| **Foreground** (default) | `SendInput` with scancodes | Input indistinguishable from a real keyboard and mouse. Always works, but ARK has to be in front. The macro pauses by itself when you switch away and resumes when you come back. |
| **Background** | `PostMessage` to the HWND | Lets you use the PC while farming, **but** Unreal normally reads Raw Input and ignores these messages. Test before trusting it: if nothing happens in game, go back to foreground. |

There is no reliable way to click into a UE5 game in the background without
injecting into the process, which is what anticheat looks for. The realistic
path to "farm while I use the PC" is a second machine or a VM.

## Settings that usually matter

- **Min/max speed (cps)**: drawn at random on every click so the rhythm is not
  metronomic. Hold time counts towards the period, so 9 cps really is 9 cps.
- **Micro pauses**: a short breather every N clicks.
- **Run every N clicks** / **Farm for at least**: the default trigger, 14
  clicks and 20 s. Both have to be met, because a click is not a landed hit.
- **Inventory waits**: raise them on a laggy server. A filter that has not
  refreshed yet is the usual cause of dropping the wrong thing.
- **Presses to close**: two with `Esc` (one to leave the search field, one to
  close), one with the inventory key. If a pass ever ends with the inventory
  still up, this is the setting to raise.
- **Wait after closing**: two seconds by default, the pause before farming
  resumes. Raise it if the panel is still fading when the first swing goes out.
- **Backspaces to clear**: must be longer than your longest keyword.
- **Unicode typing**: only if the search field ignores the letters.
- **Window title**: the fragment is matched against every open window, so keep
  it specific. A folder named `ark-something` open in Explorer matches `ARK`
  too — the app prefers an exact title, then a prefix, then the largest window,
  and **Find the ARK window** tells you which one it picked.

## Layout

```
main.py                  entry point
arkmacro/winapi.py       SendInput / PostMessage / window lookup (pure ctypes)
arkmacro/hotkeys.py      RegisterHotKey on its own thread
arkmacro/engine.py       farm <-> drop state machine
arkmacro/config.py       config.json persistence, migrates older formats
arkmacro/presets.py      ARK template library plus risk notes
arkmacro/layout.py       HUD geometry model (estimate / rescale points)
arkmacro/updater.py      self-update by fast-forwarding this clone
arkmacro/ui/picker.py    frozen-screen point picker with magnifier
arkmacro/ui/backdrop.py  gradient, glows and the brand melt
arkmacro/ui/icons.py     vector icons drawn with QPainter
arkmacro/ui/             theme, widgets and the main window (PySide6)
assets/brand.png         backdrop image (yours to replace)
tests/                   engine, UI, updater and window-matching suites
```

Generated at runtime: `config.json`, `state/` (point thumbnails), `captures/`
(dry-run screenshots).

Run the tests — they never send a real click:

```bash
python tests/test_engine.py
python tests/test_ui.py
python tests/test_updater.py
python tests/test_winapi.py
```

## Before you use it

Input automation is against the rules of most official servers and can get you
banned. On single player, your own server or a cluster that allows it, that does
not apply. Your call — just know where you stand.

[filter]: https://steamcommunity.com/app/346110/discussions/0/351660338713647819/
[language]: https://steamcommunity.com/app/346110/discussions/0/2574320091923274217/
