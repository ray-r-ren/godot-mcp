# Instant Game Studio

Describe a game and get a playable Godot 4.4 project that has been checked, run, play-tested with simulated input and, if wanted, exported for the web or Linux.

## Where to start

Call `create_game_project` with the closest starter for a new game, or `inspect_project` with the user's project zip for an existing one, and keep the `state_id` it returns.

- Pass that `state_id` to every later call. Each call that changes the project returns the updated `project.zip` and the same `state_id`.
- A local project folder must be zipped first (with `project.godot` at the zip root or in one top folder). Upload it with `upload_file` and pass the file id as `project`.
- Pick the starter from the user's words:
  - `top_down`: top-down, twin-stick, maze, "move in all directions", collect-the-coins.
  - `platformer`: side-scroller, jump and run, gravity, ledges.
  - `blank_2d`: puzzle, card, clicker, menu-driven or UI games, anything without a walking player.
  - `blank_3d`: any 3D idea.
- What every starter contains (node paths, variables, signals) is listed in [references/starters.md](references/starters.md). Read it before you write code that builds on a starter.

## Stages

1. **Start**: call `create_game_project` (name, starter, optional window size). Check `starts_cleanly: true`. For an uploaded game, call `inspect_project` (`detail: "full"` shows each scene's node tree) and note `main_scene`, `input_actions`, the scripts' methods and their variables.
2. **Build**: put the game rules in GDScript with `write_game_files` (whole files at `res://` paths, up to 50 per call; `delete` removes files). Build nodes, signals, groups and input actions with `edit_scenes` instead of hand-writing `.tscn` text.
   - `write_game_files` compiles every `.gd` it writes. Fix each `script_errors` entry (path + line) before going on.
   - `edit_scenes` is all-or-nothing. When `failed_op` is set nothing was saved. Its message lists the scene's real node paths, so fix that op and send the whole batch again.
   - Write the method first, or in the same round, when you connect a signal to it. `connect_signal` accepts a method that doesn't exist yet and only notes it; `check_project` then reports it as an error.
3. **Check**: call `check_project` until `verdict` is `ready`. It compiles every script, loads and instantiates every scene, and reports missing scripts or resources, signal connections to missing methods, and a bad main scene, each with file and line.
4. **Run**: call `run_game` with `seconds` 3–5 and a few `screenshot_at` times. Confirm `crashed: false`, an empty `runtime_errors` and `finished: true`, and look at the screenshots yourself. Use `record_video: true` when the user wants to see motion.
5. **Play-test**: call `playtest_game` with steps that act out what the user asked for, each followed by an `assert` on live state, for example "collect a coin → score goes up" or "press jump → player leaves the floor". Add `screenshot` steps at key moments.
6. **Iterate**: fix with `write_game_files` / `edit_scenes`, then repeat stages 3–5 until every assertion passes and no runtime errors remain.
7. **Export** (only if asked): call `export_game` with `target: "web"` (browser, itch.io, any static host) or `"linux"`. Linux builds are smoke-run headlessly (`smoke_ok`). Web builds are only checked for their files.
8. **Hand over**: give the user the download links of the latest `project.zip` and of any export, screenshots, video or contact sheet.

## Writing play-test steps

Each step has exactly one of these keys (full syntax in [references/playtest.md](references/playtest.md)):

```json
[
  {"eval": "$Player.position", "label": "start"},
  {"action": "move_right", "hold_ms": 1000},
  {"assert": "$Player.position.x > 700", "label": "player moved right"},
  {"assert": "score >= 1", "label": "picked up a coin"},
  {"key": "Space"}, {"click": [576, 324]}, {"wait_ms": 500},
  {"wait_until": "$Player.is_on_floor()", "timeout_ms": 3000},
  {"screenshot": "after_coin"}
]
```

- Expressions run on the current scene's root. Its script variables are readable directly (`score`), `$Path` / `%Unique` reach nodes, and autoload names, `Input`, `Engine`, `InputMap` and `ProjectSettings` are available.
- Expressions can't assign. `score = 5` is a parse error. To set state for a test, call a method instead: `set('score', 5)`, `$Player.set('position', Vector2(100, 100))`.
- Game time runs at a fixed 30 fps. `hold_ms: 1000` holds the input for 30 frames, so a 300 px/s player moves about 300 px (measured: x 576 → 876).
- Work out expected values from the code before you assert. In the top_down starter the right-hand coin (Coin1) is 253 px right of the player, so `hold_ms: 1000` on `move_right` collects it.

## Examples

**"Make a game where a ball dodges falling blocks; arrow keys move it."**

1. Use `top_down`, because it already has movement in all directions on `move_left` / `move_right` with the arrow keys.
2. `write_game_files`: write a `block.gd` (an Area2D that falls each frame and emits `hit` when it touches a body in group `player`) and a new `main.gd` that spawns blocks from a Timer and keeps `var lives`.
3. `edit_scenes`: add the Timer (`add_node` with `wait_time` and `autostart`) and connect its `timeout` to the spawn method.
4. Run `check_project`, then `run_game` with `record_video: true`.
5. `playtest_game`: `wait_ms` 3000, then assert that blocks exist (`get_tree().get_nodes_in_group('blocks').size() > 0`). Hold `move_left`, then assert that `$Player.position.x` dropped.

**"My uploaded game shows a grey screen and the log has errors."**

1. Call `inspect_project` with the zip.
2. `check_project` gives errors with file and line. Fix them with `write_game_files`.
3. Look at `runtime_errors` and the screenshots from `run_game`. A flat grey frame with no errors usually means there is no Camera2D, or the nodes sit outside the 0…viewport area.
4. Add a camera with `edit_scenes` (`add_node` type `Camera2D`) or move the nodes, then repeat `run_game` and compare `mean_color`.

## Pitfalls

- **Godot 3 code fails.** `onready`, `export var`, `yield`, `KinematicBody2D`, `instance()` and `connect("signal", self, "method")` are Godot 3. Use `@onready`, `@export`, `await`, `CharacterBody2D`, `instantiate()` and `signal.connect(callable)`. Example error: `Parse Error: Unexpected identifier "onready" in class body.` Godot 3 project zips (`config_version` < 5) are refused with `godot3_project`.
- **One parse error per file.** Godot stops at the first parse error in each script, so after fixing it a later error in the same file may show up.
- **Unknown action names.** `action` steps need an action defined in the project. The error lists the real ones. Add new ones with `edit_scenes` op `add_input_action` (keys like `A`, `Space`, `Shift`, `mouse_left`).
- **Wrong node paths.** If a path is wrong, the eval error reads "Invalid named index … for base type Object" and `runtime_errors` holds `Node not found: "X"`. Get the paths from `inspect_project` `detail: "full"`.
- **Flat screenshots.** `blank: true` means the frame is one flat colour. Usually a Camera2D/Camera3D is missing or nodes sit outside the view, but a full-screen ColorRect is flagged too. Look at the image before calling it a bug.
- **Renderer.** Runs use the Compatibility renderer on a software GPU. Projects set to Forward+ or Mobile still run, with a note in `uncertain`, but lighting and effects can look different. FPS and timing numbers say nothing about real hardware.
- **Hangs.** An endless loop in `_ready()` gives `status: partial` with "The game hung: no frame was rendered". Look for `while` loops that never yield.
- **Quitting games.** If the game calls `get_tree().quit()` itself, `run_game` notes that it quit early. Playtest steps after that point don't run.
- **Logs.** "Could not set V-Sync mode" in `log_tail` is harmless in the virtual display.
- **Export.** Web exports are single-threaded and must be served over http(s). Opening `index.html` from disk (file://) does not work. Run `check_project` before exporting, because script errors still export but then fail at runtime.

## Evidence

- **Correct code:** the `check_project` verdict and its `errors` with file and line.
- **It runs:** `run_game` with `crashed`, `runtime_errors` and `frames_rendered`. Show `contact_sheet.png` or the screenshots, and `gameplay.mp4` if recorded. When the user asks what colour something is, quote the screenshot's `dominant_color` (the most common exact pixel colour, normally the background; `dominant_share` says how much of the frame it covers) rather than `mean_color`, which blends in every sprite. Colours set by scripts at start-up differ from the .tscn values, so read them from a run, not the files.
- **It plays:** every `playtest_game` assertion with its label, `passed` and the measured `value` (e.g. "score went 0 → 1", "x 576 → 876"), plus the named screenshots.
- **The build:** `export_game` `files` with sizes, and `smoke_ok` for Linux.
- Never say a game "works" or "is fixed" without a passing play-test of the behaviour the user asked for. Report failing assertions and step errors as they are.

## Done when

- `check_project` returns `verdict: ready`.
- `run_game` shows `crashed: false`, no `runtime_errors`, and screenshots that show the game.
- `playtest_game` passes an assertion for each behaviour the user asked for, with `assertions_failed: 0` and no runtime errors.
- The user has the final `project.zip` link (and the export zip if asked). Before you replace or delete user files with `write_game_files` `delete`, confirm with the user. Their original upload stays untouched, and earlier `project.zip` links still hold earlier versions if a change has to be rolled back.

## Can't do

- Open the Godot editor or keep a live connection between calls. Each call starts the game afresh. Put a whole interaction in one `playtest_game` call.
- Export to Windows, macOS, Android or iOS. Offer the web build (runs in any browser) or the Linux build. The project zip opens in the Godot 4.4 editor, which can export elsewhere.
- Download Asset Library add-ons, art or audio from the web. Ask the user to put assets into the project zip they upload.
- Make original art or music. Starters use coloured shapes. The user can add their own images and sounds to the zip.
- Run C#/.NET (Mono) projects or GDExtension native code. Only GDScript.
- Measure real performance or FPS. Rendering is software-only.
- Open Godot 3.x projects. Convert them with the Godot 4 editor's project converter first, or rebuild with `create_game_project`.
