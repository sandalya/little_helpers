# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versions are
git tags (`vMAJOR.MINOR.PATCH`), newest first.

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

[1.1.1]: https://github.com/sandalya/little_helpers/releases/tag/v1.1.1
