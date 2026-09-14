# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versions are
git tags (`vMAJOR.MINOR.PATCH`), newest first.

## [2.1.1] - 2026-09-14

Version bump only, no functional changes.

## [1.3.0] - 2026-09-12

### Added

- Flip Viewers (`F2`): toggles a horizontal mirror on every open Viewer
  at once. Goes through each Viewer's built-in input-process slot (a
  shared `Mirror2` node, `flop` knob) rather than a node spliced into
  the graph, so it never touches a render and can't leak into a saved
  script. A new Viewer created while the flip is on joins it
  immediately.

## [1.2.0] - 2026-09-12

### Changed

- Alt+V redesigned as a standalone "Repath Paste" command, no longer
  overriding native Edit/Paste -- plain `Ctrl+V` works normally again.
- Repath Paste moved into the Little Helpers submenu, alongside the
  other tools.
- Renamed "Create/Change Layer Branch/Version" to "Create/Change Render
  Branch/Version" throughout the menu (identifiers/files unchanged).

### Known issues

- The "Little Helpers" submenu icon (added this release) doesn't show
  on pc137 -- root cause understood, not fixed: it depends on
  little_helpers registering its menu before anything else touches the
  same submenu name. Tracked alongside the studio pipeline update this
  depends on.

### Fixed

- Stale tool-count/scope claims corrected in README and the TD
  integration doc.

## [1.1.1] - 2026-09-12

### Added

- Paste-time repath (Alt+V) now shows a colour-coded PySide dialog
  instead of a plain `nuke.ask()` text blob: green count for
  auto-resolved reads, one dropdown per *layer* (not per Read/pass) for
  anything ambiguous or with no match in the current shot.

### Changed

- Repath-on-paste moved off `Ctrl+V` onto `Alt+V`, freeing plain Ctrl+V.
- Shift+E's cross-shot ambiguous-match detection now shares the same
  candidate-lookup (`layer_branch._find_layer_candidates`) as the paste
  dialog, instead of its own thinner check.

### Fixed

- `reload_all()` was missing `repath_ui` from its module list, so a
  dev-session edit to that file could be silently ignored until Nuke
  restarted.

[2.1.1]: https://github.com/sandalya/little_helpers/releases/tag/v2.1.1
[1.3.0]: https://github.com/sandalya/little_helpers/releases/tag/v1.3.0
[1.2.0]: https://github.com/sandalya/little_helpers/releases/tag/v1.2.0
[1.1.1]: https://github.com/sandalya/little_helpers/releases/tag/v1.1.1
