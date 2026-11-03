## v2
- You can now read the full text of any script or scene in a project, and fix just the broken lines of a script without rewriting it, so your own game logic stays exactly as you wrote it.
- Editing scenes in a project whose scripts are still broken no longer loses values set in the scene (such as a coin worth 3 points); they are kept and listed.
- Once a repaired project checks clean, the result lists every problem that was fixed along the way, so the user gets a complete "what was wrong" report.
- Errors from old Godot 3 code now say what to write instead (for example "@onready var"), and a signal connected to a missing function names the node, signal, function and script.
- Checking a project now lists each real problem once (for example a missing script is no longer repeated by every scene that uses it), so the list of things to fix is shorter and clearer.
- When a game's start scene is missing, the check now names the scenes you can pick instead.
- The guide now walks through the check-and-fix loop step by step, including connecting a timer or button to code you haven't written yet.

## v1
- Describe a game and get a working Godot 4 project, started from a top-down, platformer, blank 2D or blank 3D template with movement and controls already set up.
- Add game logic and build scenes (nodes, signals, controls, groups, collisions) in one go, with code mistakes reported straight away by line.
- Check a whole project for errors before playing it, including missing files, broken connections and old Godot 3 code or node names, with the file and line of each problem.
- Run the game and see it: screenshots at chosen moments, a contact sheet, the console log, crash details, the background colour of each frame and an optional short video.
- Play-test the game with simulated key presses, actions and clicks, read live values such as the score or the player's position, and get a pass/fail for each check.
- Open an existing project and get a map of its scenes, scripts, controls and autoloads.
- Export a build that plays in a web browser (ready for itch.io or any static web host) or a Linux executable.
