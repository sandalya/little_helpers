"""
little_helpers

Self-contained Nuke artist tools: Create Layer Branch (Shift+A), Change
Layer Version (Shift+E), Split Layers (F10). No MCP, no network, no
server -- copy this folder into ~/.nuke/ and call register_menu() from
menu.py. See README.md for the two-line install.

Invariant: this package imports nothing outside itself. Anything that
wants to use it imports it -- never the other way around.
"""

import nuke

from .layer_picker_ui import show_layer_picker

__version__ = "1.1.1"

LAYER_PICKER_MENU_PATH = "Little Helpers/Create Layer Branch"
VERSION_HUD_MENU_PATH = "Little Helpers/Change Layer Version"
SPLIT_LAYERS_MENU_PATH = "Little Helpers/Split Layers"

# A brand new menu entry, NOT an override of Nuke's own built-in
# Edit/Paste (nuke.menu("Nuke"), not nuke.menu("Nodes") like the three
# paths above -- same "wrong top-level menu" gotcha as the Shift+D
# collision elsewhere in this project's history, so this still isn't
# filed under "Little Helpers/..."). First version of this (2026-09-11)
# did override Edit/Paste itself and rebind it to Alt+V, which meant
# plain Ctrl+V lost Nuke's native paste and needed its own restore
# command -- unnecessary complexity Sashok caught 2026-09-12: nothing
# about Alt+V required touching Edit/Paste at all, since Alt+V was never
# claimed by Nuke natively. This way Edit/Paste (Ctrl+V) is never
# touched, ever -- no override, no restore, no risk of the two drifting
# out of sync with whatever Nuke's own native paste does in a future
# version. See repath.py.
REPATH_PASTE_MENU_PATH = "Edit/Repath Paste"


# ---- Version manager hookup (Function 2, Shift+E) ------------------------
# Calls the standalone veriter tool (little_helpers/veriter/) unmodified --
# same lazy-import pattern as split_layers below, so both self-contained
# tool subpackages stay consistent.

def show_version_hud():
    """Shift+E -- standalone entry point, runs on selected/visible Reads."""
    from .veriter.version_ui import show_version_hud as _show_version_hud
    _show_version_hud()


# ---- Split layers hookup (Function 1 checkbox + standalone F10) ---------
# little_helpers/split_layers/ reuses the pipeline's own split_layers
# package (pl_scripts.split_layers, same imported instance) for the UI and
# layer-collection side; only node-graph spacing (split_layers/
# nuke_actions.py) stays a local copy, a deliberate divergence rather than
# a duplicate -- see that module's own comments. This function stays thin
# glue only (optional node selection + the call), no split_layers logic
# ported in here.

def run_split_layers(node):
    """Function 1's "Split layers" checkbox -- selects `node` (the branch's
    last node) before launching the tool on it."""
    from .split_layers import split_layers
    for n in nuke.allNodes():
        n.setSelected(False)
    node.setSelected(True)
    split_layers.main()


def show_split_layers():
    """F10 -- standalone entry point, runs on whatever is already selected."""
    from .split_layers import split_layers
    split_layers.main()


# ---- Repath-on-paste hookup (Alt+V, standalone command) -------------------
# See repath.py for the actual detection/repath logic. This stays thin glue
# only, same lazy-import pattern as show_version_hud/show_split_layers above.

def paste_and_maybe_repath():
    """Alt+V -- pastes normally, then checks the pasted selection for
    cross-shot Reads / stray history Reads. See repath.py."""
    from .repath import paste_and_maybe_repath as _paste_and_maybe_repath
    _paste_and_maybe_repath()


def register_menu():
    """Idempotent -- safe to call repeatedly without piling up duplicate
    menu entries (removes each old item first, if present)."""
    menu = nuke.menu("Nodes")

    if menu.findItem(LAYER_PICKER_MENU_PATH):
        menu.removeItem(LAYER_PICKER_MENU_PATH)
    menu.addCommand(
        LAYER_PICKER_MENU_PATH,
        "import little_helpers; little_helpers.reload_all(); "
        "little_helpers.show_layer_picker()",
        "shift+a",
    )

    if menu.findItem(VERSION_HUD_MENU_PATH):
        menu.removeItem(VERSION_HUD_MENU_PATH)
    menu.addCommand(
        VERSION_HUD_MENU_PATH,
        "import little_helpers; little_helpers.reload_all(); "
        "little_helpers.show_version_hud()",
        "shift+e",
    )

    if menu.findItem(SPLIT_LAYERS_MENU_PATH):
        menu.removeItem(SPLIT_LAYERS_MENU_PATH)
    menu.addCommand(
        SPLIT_LAYERS_MENU_PATH,
        "import little_helpers; little_helpers.reload_all(); "
        "little_helpers.show_split_layers()",
        "F10",
    )

    # Own new command, Edit/Repath Paste -- Edit/Paste (Ctrl+V) itself is
    # never touched, see REPATH_PASTE_MENU_PATH's comment above.
    nuke_menu = nuke.menu("Nuke")
    if nuke_menu.findItem(REPATH_PASTE_MENU_PATH):
        nuke_menu.removeItem(REPATH_PASTE_MENU_PATH)
    nuke_menu.addCommand(
        REPATH_PASTE_MENU_PATH,
        "import little_helpers; little_helpers.reload_all(); "
        "little_helpers.paste_and_maybe_repath()",
        "Alt+V",
    )


_RELOAD_ORDER = (
    "nuke_utils", "hud", "layer_branch",
    "veriter.versions", "veriter.version_ui",
    "layer_picker_ui",
    "split_layers.nuke_actions", "split_layers.split_layers",
    "repath_ui", "repath",
)


def reload_all():
    """Dev loop: reload every submodule bottom-up, then this package, so the
    menu command strings pick up new code without restarting Nuke. Order
    matters -- a module must be fresh before its importers rebind from it."""
    import importlib, sys
    for name in _RELOAD_ORDER:
        mod = sys.modules.get(f"{__name__}.{name}")
        if mod is not None:
            importlib.reload(mod)
    importlib.reload(sys.modules[__name__])
