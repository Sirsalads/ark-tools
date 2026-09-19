# A.N.S Tools — the whole thing, from the first click

This is the guide. It starts at "you have just downloaded a folder" and ends at
"it is farming while you do something else." The [README](README.md) is the
reference — it explains *why* things work the way they do. This explains *what to
do*, in order.

---

## What this app is for

ARK makes you do three tedious things over and over:

1. **Swing at a rock or a tree, hundreds of times.** Your hand gets tired and
   your bag fills up with junk you did not want.
2. **Empty that junk out**, one stack at a time, so you can keep harvesting.
3. **Eat and drink** while you do it, or you die next to a full inventory.

A.N.S Tools does all three, on its own, while you watch a video on the other
monitor. It also has two tools for other jobs: emptying a container fast, and
using every stack of a chosen dye on the Apply Dye screen.

**It is three separate macros. They do not depend on each other, and you can use
one and ignore the others.**

| Macro | What it does | When you use it |
|---|---|---|
| **Farm** | Swings for you, and every so often opens the inventory and throws out what you listed | Long harvesting sessions |
| **Drop** | Sweeps the cursor across a block of slots, dropping every stack | Emptying a forge or a bag by hand, fast |
| **Overcap skin** | Paints 100 times, selects the next dye stack, and repeats | Using all stacks of a chosen dye |

Everything runs by moving your real mouse and pressing real keys. **ARK has to be
the window in front.** The app is not reading the game's memory and not injecting
anything into it — it is doing what your hand would do, faster and without
getting bored.

---

## Step 1 — Open it

**Double-click `Start.bat`.** That is the whole install.

You do not need Python. You do not need to open a terminal. You do not need
administrator rights. The first run works out what the machine has, downloads a
private Python into the app folder if there is not a usable one, installs what it
needs beside it, and opens the window. It takes a minute or two and shows you
what it is doing.

Every run after that starts immediately.

Everything it downloaded lives **inside the app folder**. Nothing was added to
your PATH, nothing was installed for other users, and deleting the folder removes
all of it.

> **If the window does not appear**, the app will tell you why. A start that
> fails puts a message box on screen and writes the whole reason to
> `state\startup-error.txt`, and the command window stays open with the last
> lines of it rather than closing on you.
>
> To look at the machine without starting anything — it changes nothing and
> prints what it found:
>
> ```
> powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -CheckOnly
> ```

---

## Step 2 — Run the display check, once

**Settings → Check this display.** It takes a second and writes its answer to the
**Log** page.

Do this before anything else on a new machine. Everything the app stores — where
the buttons are, which slots to sweep — is a screen coordinate, and displays lie
about coordinates in ways that are invisible until something lands in the wrong
place. The check measures your setup and tells you whether the app and Windows
agree:

```
--- display check ---
DPI awareness: per-monitor v2
primary screen reports 1920x1080 px
screen 1 (primary): 1920x1080 logical at (0, 0), 1x scaling -> 1920x1080 physical
cursor at (1231, 621) round-trips through 1x scaling to (1231, 621)
  -- picked areas will land where you drag them
screen reads fine at (1231, 621): (34, 38, 44)
--- display check done ---
```

Two things are being measured, and both matter. The **round trip** says picked
areas will land where you drag them. The **screen read** says the app can see
your screen at all — which every safety check in the app depends on, since the
only way it knows a keyword reached the search box is by looking.

**Green last line: you are fine, forget this page exists.** Red: send those lines
along with any bug report, because they say exactly what is different about your
machine.

> If the screen-read line is red, the drop passes will refuse rather than drop
> blind, and the log will say the same thing. Run ARK in **borderless**, not
> exclusive fullscreen.

---

## Step 3 — Set up the Farm macro

This is the big one, and it is one page: **Farm**. Work down it in order.

### Run ARK in borderless or windowed mode

Not exclusive fullscreen. The app has to be able to capture and draw over your
screen to let you pick things, and exclusive fullscreen refuses both.

### 3.1 — Swinging

How fast it clicks. The speed is drawn at random between the two bounds on every
click, so the rhythm never becomes a metronome. The defaults (6–9 per second) are
fine for almost everything.

**Micro pauses** adds a short breather every N clicks. Off by default.

### 3.2 — When it empties the bag

How often it stops swinging to run a drop pass. The default is **every 14 clicks,
and at least 20 seconds of farming** — both have to be true.

Why both: clicks are not swings. A dino with its own attack cooldown eats fourteen
clicks in two seconds and lands three hits. The time floor makes sure real
harvesting happened before the inventory opens.

You can also switch it to a plain timer, or to **Hotkey only** if you would rather
press `F7` yourself.

### 3.3 — What to drop

This is the part that can cost you things. Read it properly.

Each row is a **keyword typed into ARK's inventory search**, and then **Drop All**
is clicked. ARK's search is a **"contains" match**: it lists every item whose name
contains what you typed, and Drop All drops everything listed.

So `stone` also lists **Stone Pick** and **Stone Hatchet**. If those are in your
bag, they go on the ground.

| Keyword | Also catches | |
|---|---|---|
| `stone` | Stone Pick, Stone Hatchet | risky |
| `metal` | Metal Pick, Metal Hatchet, metal armor, Metal Ingot | risky |
| `wood` | Wooden Club, wooden structures | risky |
| `hide` | Hide Shirt, Hide Pants | risky |
| `berry` | Mejoberry, Narcoberry | risky |
| `thatch` `fiber` `flint` `keratin` `chitin` `pelt` | nothing else | safe |

Rows the app knows are risky are marked with a **⚠** and turn amber. **Presets**
opens a library of ARK resources grouped by what you are farming, with the same
warnings attached.

Two rules that keep you out of trouble:

- **Carry nothing you cannot afford to lose.** Good tools, cementing paste,
  kibble — put them in a box before you arm the macro.
- **Prefer long, unambiguous keywords.** `flint`, `keratin`, `obsidian`, `pelt`.

Only checked rows run, in list order.

### 3.4 — Before every Drop All

Leave this on.

Between typing a keyword and clicking Drop All there used to be nothing but a
half-second wait and hope. If the click missed the search box, or the window lost
focus for a frame, the box stays **empty** — and **Drop All with an empty search
box empties your entire inventory**.

With this on, **one thing** has to be true before any Drop All click goes out:
the keyword is visibly in the search box. The app reads a band of pixels across
the box before and after typing, and counts how many of them changed. A word
moves a few. If not enough moved, it skips the drop and says so in red, with the
numbers:

```
"stone" never reached the search field — Drop All skipped (0 of 45 samples changed, a keyword is 3-31)
```

There is a ceiling as well as a floor, and it is the important one. If the
inventory panel arrives *between* the two readings, every pixel in the band
changes while the search box is still empty — so a check with no ceiling would
wave that through and Drop All would take the whole bag. Too many changed is not
a word, it is the screen repainting, and it is refused.

And the box has to be **empty before the keyword goes in**, which is checked
rather than assumed. ARK clears its own filter when Drop All fires, but not
instantly — under lag the box still shows the *last* keyword while the next one
is typed, and then the old word vanishing counts as exactly as much change as a
new word arriving. Counting cannot tell those apart, so the app remembers what
the box looks like empty and makes sure it matches before typing. If it does
not, it wipes and looks again:

```
the search box still holds the last keyword — the game has not caught up with
its own Drop All. Wiping before typing the next one
```

The app also waits for the inventory panel to appear rather than trusting a fixed
delay, and that helps — but it is a **second opinion, never a veto**. If it cannot
confirm the panel it says so and carries on, because a keyword typed at a panel
that is not there moves nothing in the band and the check above refuses on its
own. Anything allowed to block every drop has to be something that cannot be
wrong.

It sees *that* there is text, not *which* text — so it is a floor, not a
guarantee. The two rules above still apply.

**It needs to be able to read the game.** In exclusive fullscreen Windows returns
no pixels, the check cannot run, and rather than drop unverified the macro
**holds the drop back and says so in red**. If every pass is refusing, that is
what happened: switch ARK to borderless.

On **background delivery** the rule is simple: **keep that ARK window in view**.
Not focused — visible. On two monitors, farm on one and play on the other and
every check works, because the pixels on screen where the macro looks really are
the game. Only something drawn *on top* of it breaks that, and then the log names
the window that is in the way rather than guessing.

The app takes itself out of that picture: hitting Start on a background run
minimises this window if it was sitting over the two captured points, with a line
saying so. It does not need to be on screen — the hotkeys are global and the log
is all still there when you bring it back.

**A one- or two-letter keyword is flagged, not blocked.** `o` lists Stone, Wood,
Cooked Meat, Hide Boots and most of your bag, and Drop All takes all of it. That
is a typo about as often as it is the whole point: `o` while farming metal drops
everything and keeps **Metal** and **Element Shard**, which have no `o` in them,
and your metal tools survive for the same reason. So the app marks the row amber
and runs it. Dry-run a new one once and you will see exactly which side it is.

### 3.5 — Dry run

Runs the whole cycle — opens, filters, types — and **never clicks Drop All**.
Instead it saves a screenshot of the filtered inventory to `captures/`.

**Use it once whenever you add a keyword.** It shows you exactly what would have
fallen, without anything falling.

### 3.6 — Inventory and timings

Leave these alone unless something is off. Raise the waits if your server is
laggy: a filter that has not refreshed yet is the usual cause of dropping the
wrong thing.

### 3.7 — Auto-feed

Presses two hotbar slots on a timer so your character eats and drinks. Food on one
slot, a full waterskin or canteen on the other; **every 6 minutes**, slots **4**
and **5** by default.

It fires from inside the farming loop, so it can never land while the search box
has the keyboard — a hotbar key typed into the filter would become a digit in
your keyword.

It cannot see your food bar. It presses the slot; an empty slot presses nothing.
Keep the stack topped up, and make sure your drop list does not throw away the
food it is pressing.

### 3.8 — Stop on an icon

Some things clicking cannot fix — a broken pick, an overloaded character, a dead
mount. The game only ever says so with an icon on screen, and the macro has no
way to read the game. So show it the icon once.

1. Get the icon on screen in ARK.
2. **Farm → Stop on an icon → Capture the icon.** The screen freezes; drag a box
   **tight around the icon and nothing else**.
3. Turn on **Stop when the icon appears**.

From then on it looks at that box between clicks, and the moment the icon is back
it stops the macro — exactly what pressing `F6` does, except immediately.

**The icon has to be on screen when you capture.** That is the one way to get
this wrong — there would be nothing to look for, and the macro would watch an
empty box forever. The app checks and refuses in red.

It does not store a picture. An ARK icon is drawn over the live 3D scene, so half
of any box around it is rock and sky that change every frame; comparing colours
drifts with the weather. It stores the **shape** — which samples stand out from
the rest of the box, and which way — and the background is never compared. So the
same icon is found over rock, over sky, over water, and at night.

**Capture it where you actually farm.** A near-black icon over a near-black cave
has little left to stand out from — that is the one real limit. If it misses
where you play, lower *Contrast needed*; scenery on its own never triggers it at
any setting, so going low costs nothing.

Two dials if it misbehaves. **Never triggers** → lower *Contrast needed* (capture
tells you the margin and how much is to spare) or lower *Match needed*.
**Triggers on its own** → raise *Match needed*, or drag a tighter box.

If it ever stops being able to see that corner — something covering it, the game
going exclusive fullscreen — it says so **in red** rather than quietly carrying
on. A guard that stops working without telling you is the thing this exists to
prevent.

It never looks during a drop pass, never while ARK is not in front, and a screen
it cannot read is never a sighting.

### 3.9 — The two points it clicks

A drop pass clicks two things: the **search field**, then the **Drop All**
button. Where those sit depends on your resolution and on what the HUD is
showing, so you capture them once.

1. **Open the inventory in ARK** — exactly the way the macro will. Alone with
   `I`, or with a storage box open. The icon row sits in a different place in
   each.
2. **Press `F9`.** The window hides, the screen freezes, and a magnifier follows
   your cursor.
3. **Click the search field, then Drop All.** Drop All is the second icon of the
   row, right next to the crossed arrows that mean *transfer all*. Arrow keys
   nudge one pixel, `Shift`+arrow ten, `Enter` confirms, `Esc` cancels.

Each captured point keeps a zoomed thumbnail of what you targeted, and **Test**
moves the cursor there without clicking so you can check it.

No screenshot possible? **Estimate points for this resolution** computes a
starting guess — then verify it with Test.

### 3.10 — Start it

Back to **Dashboard**, press **Start macro** or `F6`.

Bring ARK to the front and stand where you want to harvest. The macro pauses by
itself the moment ARK is not the front window and picks up again when it is.

Watch the first drop pass go by on the Log page. It narrates every step.

---

## Step 4 — The Drop macro (optional)

Nothing to do with farming. You are standing at a forge with 300 slots of ingots
and you want a block of them on the ground.

**Drop → Freeze screen and select the block.** Drag a box over the slots. The
sweep path is drawn inside it as you drag — a dot on every slot the cursor will
stop on, an orange dot where it starts. If the dots do not land on slot centres,
change **Columns** and **Rows** and drag again.

Then pick how it runs:

| Mode | You | The app |
|---|---|---|
| **Press to start and stop** | press `F3`, press again when done | sends the drop key, once per slot |
| **Hold the activation key** | hold `F3` | sends the drop key, once per slot |
| **Hold the drop key yourself** | hold `O` | sends nothing — your finger is the instruction |

The first is the default and the one to use: your hands stay free.

**Two different keys, on purpose.** `F3` is yours and only tells the app to
start. `O` is the game's — the key ARK acts on. Setting the activation key to the
drop key is refused, because pressing the very key the macro exists to send is a
circle.

It refuses to run while the Farm macro is going: an autoclick loose in an open
inventory moves items around instead of dropping them. Stop the farm first.

---

## Step 5 — The Overcap skin macro (optional)

Open **Apply Dye** in ARK and filter the dye list to the color you want to use.
As each stack disappears, the next one must move into the same first slot.

On **Overcap skin**, capture two points from the frozen screen:

1. The **upper color region** you want to click repeatedly.
2. The **colored center of the first dye icon** in the list below. Click the
   dye itself, away from the quantity text and slot border; this also captures
   its color for the check that tells when it is gone.

Capturing the two points switches the macro on. Return to ARK and press
**`F4`**. It selects the first dye,
clicks the upper point **100 times**, then selects the next stack at the same
lower point and repeats. You do not need to count your stacks or select them
one by one. The macro finishes when the first slot has no matching dye for
**three consecutive readings**.

Keep the list filtered to the dye you captured: a different color will not
match that reference. Partial stacks such as **x97** work too; the macro sends
100 attempts before selecting again. It does **not** read the quantity with
OCR, so its counter is click attempts, not a confirmed total of dyes consumed.

Out of the box it clicks **as fast as it can** (time between clicks **0**) and
goes from one stack to the next **without pausing**: 100 clicks, read the
slot, select, keep clicking. The game will not take a few hundred clicks a
second and does not need to — clicks it drops cost nothing, the stack is just
selected again. Raise **Time between clicks** only if the game visibly misses
clicks, and **Pause before the next stack** only if the list updates slowly.
GeForce NOW's configured stream latency is added to the pause.

Press **`F4` again to stop**, or **`F8` for emergency stop**. It also stops if
ARK loses focus, the screen cannot be read, you disable it or close the app.
Stop Farm and Drop before starting it. Capture again after changing the dye,
HUD, game window position or resolution.

**Nothing happens when you press `F4`?** Open the **Log** page: every press
that goes nowhere says why — the switch is off, ARK is not the window in front
(it names the one that is), the farm macro is running, or the screen is frozen
for picking. The note under the switch on the Overcap skin page says the same
before you press anything.

---

## Your keys

All of them are on the **Dashboard**, drawn as keycaps with what they do beside
them. All of them are rebindable.

| Key | What it does | |
|---|---|---|
| `F6` | Start / stop the Farm macro | works anywhere |
| `F7` | Run a drop pass now | works anywhere |
| `F8` | Emergency stop | works anywhere |
| `F9` | Freeze the screen and pick | works anywhere |
| `F3` | Sweep a block of slots | only with ARK in front |
| `F4` | Start / stop painting through dye stacks | only with ARK in front |

The four global ones are registered with Windows, so they fire even while ARK has
focus and **the game never sees them**. The Drop and Overcap skin activation
keys are only watched, so they also reach ARK. Choose keys with no game binding.

---

## When something looks wrong

**Go to the Log.** Everything the app did is there, in order, with timestamps.
It says what it clicked, what it typed, whether the keyword actually reached the
search box, how many Esc presses closed the inventory, and why it refused to do
something.

Most reports answer themselves there. If yours does not, the Log is what to send.

---

## Streaming on GeForce NOW

**Settings → Where ARK runs → GeForce NOW.** The client forwards your real mouse
and keyboard to the server, so everything works — just one round trip later. The
app adds a latency allowance to every wait in the drop routine, retargets the
window, and measures the video inside the window instead of the window itself.

**Recapture your points after switching**, and raise Drop's per-slot time if it
misses slots. Overcap skin adds the configured stream latency to its click and
stack waits; increase those timings if clicks or list updates still fall behind.

Background delivery is greyed out on this profile and no setting brings it back —
the client only forwards *real* input, so a message posted to its window never
enters the stream. Farming while you use the PC needs a second machine, or ARK
streamed inside a VM.

---

## Keeping it up to date

**Settings → Updates.** It pulls straight from the repository and restarts
itself. Your config, captured points and screenshots are never touched.

**Update on its own** is on by default: it checks at startup and every 20
minutes, and updates without asking. It never restarts mid-farm — an update that
lands while the macro is running waits until you stop.

There is no review step. Whatever is published is what you farm with on the next
check. That is the point of the switch and the whole risk of it; turn it off if
you would rather press the button yourself.

---

## What it will not do

Worth knowing before you trust it with a session:

- **It does not read your inventory contents or quantities.** Its pixel checks
  recognize the panel, text appearing in the search box, a captured stop icon,
  or the chosen dye in its first slot. They do not identify everything in your
  bag or verify how many dyes each click consumed.
- **It cannot tell `met` from `metal`.** The safety check confirms *something*
  was typed, not what.
- **It cannot press an empty slot.** Auto-feed will happily press a slot with no
  food in it and report nothing wrong.
- **It cannot work through a window that is not in front.** Every macro pauses or
  refuses when ARK is not the active window. That is deliberate: the alternative
  is keystrokes landing in whatever you are actually doing.
- **It cannot undo a drop.** Which is why the search-box check exists, why dry run
  exists, and why the drop list warns you about `stone`.

---

## The short version

1. Double-click **`Start.bat`**.
2. **Settings → Check this display**, once.
3. **Farm** → pick the two points with `F9`, choose your keywords, **dry run
   them**.
4. **`F6`** to start.
5. Anything unexpected: **Log**.
