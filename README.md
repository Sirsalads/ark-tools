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

### Zero clicks: Update on its own

Same card, second switch. With it on the app checks at startup **and every 20
minutes**, then pulls and restarts without asking — a commit pushed here reaches
the running app with nothing for you to do.

What that buys and what it costs, plainly:

- There is **no review gate**. Whatever is pushed is what you farm with, on the
  next check. That is the point of the switch, and the whole risk of it.
- It **never restarts mid-farm.** An update that lands while the macro is
  running is held, with a line in the log, and applied the moment you stop.
- A **dirty checkout is skipped** entirely — the pull would refuse anyway.
- A pull that **fails** (a diverged branch, no network) stands down for the rest
  of the session instead of retrying every 20 minutes. Fix the reason and use
  the button once; the next start re-arms it.
- The clone follows **whatever branch it is on**. On `main` it tracks `main`;
  check out a feature branch and it tracks that instead. Worth knowing if the
  card ever says "you are on the latest commit" while you expect something new
  — check which branch the card names.

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
| `metal` | Metal Pick, Metal Hatchet, metal armor and structures, Metal Ingot | **high** — and no substring catches the ore alone |
| `wood` | Wooden Club, wooden structures | **high** |
| `hide` | Hide Shirt, Hide Pants (armor) | **high** |
| `berry` | Mejoberry, Narcoberry | **high** — loses kibble and narcotics |
| `thatch`, `fiber`, `flint`, `keratin`, `chitin`, `pelt` | — | ok |
| `raw meat` | does *not* match Raw Prime Meat | ok |

Ways around it:

- Farming stone? Carry **metal tools** — then `stone` is safe. The reverse does
  not work: `metal` matches the metal tools you just switched to, so empty the
  bag of metal gear before arming that one.
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
2. click the filter field;
3. type the template's keyword;
4. **read the search box** — no keyword visibly in there, no drop;
5. click **Drop All**;
6. repeat for every checked template, in list order;
7. press **`Esc` twice** to close the inventory and resume farming. Nothing
   clears the filter by hand: ARK empties the search box itself when Drop All
   fires.

## The one failure that costs the whole bag

Steps 3 and 5 used to be joined by nothing but a half-second wait, and that is a
hope, not a check. If the click missed the search field, or the window lost
focus for a frame, or the stream swallowed the burst of keys, the box stays
**empty** — and **Drop All with no filter empties the entire inventory**, tools
and all. It is the one failure of this routine that cannot be walked back.

So the box is read instead of trusted. Right after the field is focused, while
it is certainly empty, the macro samples a band of pixels across it; after
typing it samples them again. Glyphs move pixels, so the two readings **have**
to differ:

```
23:15:44 filtering "flint"
23:15:45 clicked Drop All at (1400, 900)
23:15:47 filtering "thatch"
23:15:48 "thatch" never reached the search field — Drop All skipped, the bag keeps this one
```

The mouse sits on the filter point for both readings, so whatever the cursor
covers is covered identically in both and simply carries no information — which
is why the measure is *how many* samples moved, never *all* of them.

What it does **not** do is read *which* text is in there: `met` and `metal` both
look like "not empty". A keyword that got in halfway still passes, and ARK's
filter is a "contains" match, so the two rules on the Templates tab still hold —
long, unambiguous keywords, and nothing in the bag you cannot afford to lose.

The switch is **Templates → Before every Drop All**. Turning it off does not
skip the check, it only stops it from blocking: the drop goes out anyway and the
log says the box looked empty, which is the honest way to measure how often it
trips on your connection. It needs a readable screen — borderless or windowed,
foreground delivery — and says so in the log when it cannot see.

Two presses, not one, and that is the whole trick: typing in the filter leaves
the **search field holding the keyboard**, so the first `Esc` only steps out of
the field and the second is what actually closes the panel. With a single press
the inventory stayed open and the macro kept clicking inside it — swings that
never landed on a node, and a next pass that pressed `I` into an already open
panel.

But a fixed count is the wrong tool, in both directions: one press too few and
the macro farms inside an open inventory, one too many and the spare `Esc`
reaches the game and opens the pause menu. So the macro **does not count — it
looks**. Right before closing, while the panel is certainly up, it reads five
pixels along the line from the filter field to Drop All (the panel's icon row),
then presses and re-reads until those pixels change:

```
23:15:50 closing the inventory
23:15:51 inventory still up after 1x esc — pressing again
23:15:51 inventory closed after 2x esc
```

If four presses go by with the panel still there, it tries the other key once
(the inventory key when you close with `Esc`, and the reverse) and says so in
the log. **Presses to close** (1–5, under *Templates → Inventory and timings*)
is the fallback for when the screen cannot be read — background delivery, or
exclusive fullscreen. One more reason to run **borderless or windowed**.

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

**Recapture your points after switching.** Background delivery is **greyed out**
on this profile — see below.

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
| **Background** | `PostMessage` to the HWND | Lets you use the PC while farming, **but** Unreal normally reads Raw Input and ignores these messages. Test before trusting it: if nothing happens in game, go back to foreground. Not available on GeForce NOW. |

There is no reliable way to click into a UE5 game in the background without
injecting into the process, which is what anticheat looks for.

### Why background is impossible on GeForce NOW

Not "unreliable" — impossible, and no setting brings it back. The client is not
the game: it **captures real input** from whatever has focus and forwards it
over the network. A `PostMessage` is not real input; it is a message handed to
the client's own window, where it stops. Nothing crosses to the server, and the
macro would pay every wait in the cycle to send precisely nothing. So the entry
is greyed out on that profile, and a hand-edited `config.json` that asks for it
refuses to arm with an error in the log instead of farming into the void.

What actually gets you "farm while I use the PC", in order of how well it works:

1. **A second machine.** Any old laptop, or a phone or tablet running the GeForce
   NOW app — the session is yours wherever it runs. Nothing to configure and
   nothing to defeat. This is the real answer.
2. **A Windows VM** (Hyper-V, VMware, VirtualBox) with the GeForce NOW client
   *and* this app installed **inside the guest**. The guest has its own focus and
   its own desktop, so the macro is foreground in there while you use the host
   normally. Caveats worth knowing before you spend an evening on it: the client
   may refuse to stream or fall back to a low bitrate under virtualization, and
   the VM needs enough GPU passthrough to decode the video.
3. **A second Windows user session** over RDP, same idea without the VM — but
   connecting to the console session locks your desktop, and disconnecting the
   RDP session pauses the desktop inside it. Fiddly; the VM is the better shape.

None of these is a shortcut through the client. The stream carries real input or
nothing, and that is the whole reason foreground works and background does not.

## Settings that usually matter

- **Min/max speed (cps)**: drawn at random on every click so the rhythm is not
  metronomic. Hold time counts towards the period, so 9 cps really is 9 cps.
- **Micro pauses**: a short breather every N clicks.
- **Run every N clicks** / **Farm for at least**: the default trigger, 14
  clicks and 20 s. Both have to be met, because a click is not a landed hit.
- **Inventory waits**: raise them on a laggy server. A filter that has not
  refreshed yet is the usual cause of dropping the wrong thing.
- **Presses to close**: only consulted when the screen cannot be read; normally
  the macro checks the panel and presses until it is gone.
- **Wait after closing**: two seconds by default, the pause before farming
  resumes. Raise it if the panel is still fading when the first swing goes out.
- **Only drop when the keyword reached the search box**: leave it on. It is the
  only thing standing between a swallowed keystroke and an empty inventory.
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
