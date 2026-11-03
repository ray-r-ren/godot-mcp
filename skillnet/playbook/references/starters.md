# What each starter contains

Every starter is a Godot 4.4 project with the Compatibility renderer and a 1152×648 window by default. Its main scene is `res://scenes/main.tscn`.

All starters define these input actions:

| Action | Keys |
| --- | --- |
| `move_left` | A, Left |
| `move_right` | D, Right |
| `move_up` | W, Up |
| `move_down` | S, Down |
| `jump` | Space, W, Up |
| `pause` | Escape, P |

`pause` is only an input action. No starter code pauses the game, so write that logic yourself if the game needs it.

Node paths below are relative to the main scene root `Main`, which is how `$Path` in play-test expressions sees them.

## top_down

- **Main** is a Node2D with `res://scripts/main.gd`. It has a `var score := 0` and connects every node in group `coins` to `_on_coin_collected(value)`, which adds to `score` and sets `$HUD/ScoreLabel.text` to `"Score: N"`.
- **Background** is a dark blue-grey ColorRect: `Color(0.12, 0.16, 0.22)`, measured as `#1f2a38`.
- **Coins/Coin1…Coin5** are instances of `res://scenes/coin.tscn`:
  - Coin1 (829, 324), Coin2 (322, 324), Coin3 (576, 142), Coin4 (576, 505), Coin5 (979, 129).
  - Each coin is an Area2D in group `coins`. It has `signal collected(value: int)` and `@export var value := 1`, and frees itself when a body in group `player` enters it.
- **Player** is an instance of `res://scenes/player.tscn`: a CharacterBody2D in group `player` that starts at (576, 324).
  - `@export var speed := 300.0` px/s, 8-way movement with `Input.get_vector`.
  - It is clamped to stay on screen.
- **HUD/ScoreLabel** is a Label on a CanvasLayer at the top left.

## platformer

- **Main** has the same score, coins and HUD logic as top_down, on a sky-blue Background ColorRect `Color(0.45, 0.7, 0.95)`.
- **Level/Ground**, **Level/LedgeLeft** at (288, 440) and **Level/LedgeRight** at (829, 324) are StaticBody2D platforms with a ColorRect `Visual`.
- **Coins/Coin1…Coin4** are at (288, 400), (829, 284), (714, 568) and (979, 568).
- **Player** is a CharacterBody2D that starts at (138, 548) and settles on the ground at y ≈ 576.
  - `speed := 260.0` and `jump_velocity := -560.0`, with gravity from the project settings.
  - `jump` only works when `is_on_floor()`.
  - If it falls below the screen it respawns at its start point.
- Measured: 300 ms after pressing `jump` (100 ms hold + 200 ms wait) the player is about 135 px up (y 576 → 441).

## blank_2d

- **Main** is a Node2D with an empty `_ready()` in `res://scripts/main.gd`.
- **Background** is a ColorRect `Color(0.1, 0.1, 0.14)`.
- **Title** is a centred Label showing the game's name.
- There is no player and no camera. Add nodes with `edit_scenes` and logic with `write_game_files`.

## blank_3d

- **Main** is a Node3D. Its script points `Camera3D` at the origin in `_ready()`.
- **WorldEnvironment** gives a sky-blue background and ambient light, and **Sun** is a DirectionalLight3D.
- **Camera3D** is at (0, 9, 12).
- **Ground** is a 20×1×20 green StaticBody3D box.
- **Player** is a CharacterBody3D capsule in group `player` at (0, 1, 0).
  - `speed := 6.0`, `jump_velocity := 6.5`.
  - It moves on X/Z with the `move_*` actions and respawns if it falls below y = -20.

## Building on a starter

- To keep the starter's score logic, add more coins with `edit_scenes` op `instantiate_scene` (`child_scene: res://scenes/coin.tscn`, `parent: Coins`, `properties: {"position": [x, y]}`). Main's `_ready()` connects every coin in group `coins` at start.
- Coins made later in code must be connected by your own code: `coin.collected.connect(_on_coin_collected)`.
- When you replace `main.gd`, keep `var score` if play-tests or the HUD read it.
