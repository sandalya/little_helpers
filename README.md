# little_helpers

Self-contained Nuke artist tools for building and maintaining layer-branch
comps (see `docs/NUKE_COMP_LAYER_ASSEMBLY.md` in this repo for the
comp pattern these tools assume). No MCP, no network, no server -- this
package never opens a socket and never talks to anything outside the Nuke
session it's running in.

Extracted from the `vfx-mcp` pipeline-infra repo (`github.com/sandalya/vfx-mcp`)
so it can be handed to other compositors on its own, with no MCP/socket/server
code along for the ride.

Installing this yourself on your own machine? Keep reading below.
Rolling it out pipeline-wide for other compositors? See
`docs/NUKE_PIPELINE_TD_INTEGRATION.md` in this repo instead --
it covers shared-`NUKE_PATH` placement, `menu.py` wiring, hotkey
collision checks, and which of the three tools are coupled to the
layer-branch comp convention.

## What's here

| Tool | Hotkey | What it does |
| --- | --- | --- |
| Create Layer Branch | `Shift+A` | Lists layer-branch folders under `$FTRACK_RENDER_PATH`, freshest first. Pick one to build the 4-Read (lights/beauty/tech/crypto) assembly chain for it. |
| Change Layer Version | `Shift+E` | Jump to latest / step version up / step version down on the selected Read node(s) (or, if nothing's selected, whatever Reads are visible in the Node Graph). Optional "History" checkbox keeps a row of old-version reference Reads in sync next to the live one. |
| Split Layers | `F10` | Sashok's per-lightgroup comp splitter, standalone. Also reachable as a checkbox inside the Create Layer Branch panel, which runs it on the branch it just built. |
| Repath on Paste | `Alt+V` | Overrides `Edit/Paste`. Pastes normally, then checks the pasted selection for Read nodes from another shot's render root and offers to repoint them at this shot's own renders (a dialog with one dropdown per ambiguous/unmatched layer), deletes any disconnected history Reads that came along, and relabels branch StickyNotes to match. |
| Paste (Plain) | `Ctrl+V` | Nuke's own paste, unmodified, no repath check -- exists because claiming `Edit/Paste` for the row above takes plain `Ctrl+V` with it (Nuke doesn't fall back to its native paste on its own). |

## Install

This repo's root is laid out to drop straight onto `NUKE_PATH` as-is --
the checkout folder's name doesn't matter, only its contents do:

```
<this repo>/
├── menu.py            <-- registers the tools; Nuke loads this automatically
└── little_helpers/     <-- the actual package
```

1. Clone or copy this repo somewhere on `NUKE_PATH` (any folder name works,
   e.g. `~/.nuke/little_helpers-repo/` -- Nuke finds `menu.py` and the
   `little_helpers` package inside it regardless of what the checkout itself
   is called).
2. Restart Nuke. The three tools appear under the `Little Helpers` menu in
   the Node Graph, with the hotkeys above.

That's the entire install. Nothing else needs to run, nothing else needs
to be configured, and nothing in this package binds a port or reaches
outside the Nuke process.

If `menu.py` can't sit directly on `NUKE_PATH` (e.g. a shared pipeline
`menu.py` already exists), add its two lines to that file instead:

```python
import little_helpers
little_helpers.register_menu()
```
-- as long as this repo's root (the parent of the `little_helpers/`
package folder) is on `NUKE_PATH` so the import resolves.

## Notes

- Menu registration is idempotent -- `register_menu()` can be called again
  (e.g. after a `reload_all()`) without piling up duplicate menu entries.
- `reload_all()` is a dev-loop convenience: it reloads every submodule of
  this package (in dependency order) plus the package itself, so edited
  code goes live on the next hotkey press without restarting Nuke. Not
  needed for normal use -- Nuke's own module caching handles everything
  once the package is installed and Nuke is running.
