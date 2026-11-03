# Play-test step reference

`playtest_game` starts the game, normally from the main scene or from the scene you name in `scene`, in a virtual display. It runs at a fixed 30 fps and plays your steps in order, each one finishing before the next starts.

All times are game time: 1000 ms is always 30 frames, however slow the machine is. The project files are not changed.

## Steps

Each step uses exactly one of these keys. Add `label` to any step to name it in the results.

| Step | What it does | Fields |
| --- | --- | --- |
| `{"action": "jump"}` | Presses an input action, holds it, releases it, then waits 1 frame. | `hold_ms` (default 100) |
| `{"key": "Space"}` | Presses a key by name: `A`–`Z`, `0`–`9`, `Space`, `Enter`, `Escape`, `Tab`, `Shift`, `Ctrl`, `Alt`, `Left`, `Right`, `Up`, `Down`, `F1`… | `hold_ms` |
| `{"click": [x, y]}` | Mouse press and release at window pixel x, y. | `button`: left / right / middle |
| `{"wait_ms": 500}` | Lets the game run with no input. | |
| `{"screenshot": "name"}` | Saves `name.png`. The name may use letters, digits, `-` and `_`. | |
| `{"eval": "expr"}` | Reads live state. The result is in `value`. | |
| `{"assert": "expr"}` | Passes when the expression is true. The result is in `passed`, and `value` holds what it evaluated to. | `label` |
| `{"wait_until": "expr"}` | Runs frames until the expression is true. It is a step error if it is still false at the limit. | `timeout_ms` (default 5000) |

Notes:

- `action` steps need an action that exists in the project. The error lists the defined ones.
- `key` steps work for code that reads keys directly or through actions bound to that key.
- A failing `assert` or a step error doesn't stop the play-test. Later steps still run.

## Expressions

Expressions are Godot `Expression` syntax, evaluated on the current scene's root node:

- **Variables** of the root's script by bare name: `score`, `lives`, `game_over`.
- **Nodes**: `$Player`, `$HUD/ScoreLabel.text`, `%UniqueName` and `get_node("Path")`.
- **Methods**: `$Player.is_on_floor()`, `get_tree().get_nodes_in_group("coins").size()`, `get_tree().current_scene.name`.
- **Autoloads** by name: `GameState.level`.
- **Singletons**: `Input`, `Engine`, `InputMap` and `ProjectSettings`, e.g. `Input.is_action_pressed("jump")`.
- **Constructors** such as `Vector2(…)`, `Vector3(…)` and `Color(…)`, and maths such as `$Player.position.distance_to(Vector2(0, 0))`.

What an expression can't do:

- **No statements.** You can't assign (`score = 5` is a parse error), and you can't use `var`, `if` or loops. To set state, call a method: `set("score", 5)`, `$Player.set("position", Vector2(100, 100))`, `$Player.call("die")`.
- **Integer division by zero fails.** For example, `1/0` is an evaluation error.

How results come back:

- `Vector2` / `Vector3` → `[x, y]` / `[x, y, z]`.
- `Color` → `"#rrggbbaa"`.
- Node → `{"node", "class", "path"}`.
- Arrays and dictionaries → the first 50 items.

## Reading the result

- `assertions_passed` / `assertions_failed` count `assert` steps only.
- `step_errors` counts steps that couldn't run: unknown actions or keys, parse errors, evaluation errors, and `wait_until` timeouts.
- `runtime_errors` holds engine errors raised while the game ran. `step` is the step that was running at the time, so an error during a `wait_ms` blames that wait.
- If the game quits by itself or crashes mid-way, `steps_run` is less than `steps_total`, `status` is `partial`, and `uncertain` says which happened. `crashed` is true only for a crash (non-zero exit).

## Example: does collecting a coin raise the score? (top_down starter)

```json
[
  {"eval": "score", "label": "score before"},
  {"action": "move_right", "hold_ms": 1000},
  {"assert": "score == 1", "label": "coin collected"},
  {"assert": "$HUD/ScoreLabel.text == 'Score: 1'", "label": "HUD updated"},
  {"assert": "get_tree().get_nodes_in_group('coins').size() == 4", "label": "coin removed"},
  {"screenshot": "after_coin"}
]
```

All three assertions pass on the unmodified top_down starter.
