"""
little_helpers.viewer_flip

F2 -- toggles a horizontal mirror on every Viewer at once. Goes through
each Viewer's built-in "input process" slot (the `input_process` /
`input_process_node` knobs Nuke uses for viewer-only LUT/CDL preview), not
a Mirror2 spliced into the actual node graph: an input-process node is
never connected to anything, is skipped by Write/render evaluation, and
can't leak a flipped frame into a render if someone saves mid-flip. One
shared Mirror2 feeds every Viewer's slot -- toggling it is one node
edit, not N.

State (on/off) lives on the `nuke` module object, not a plain module
global -- `reload_all()` re-executes this module's top level on every
hotkey press (see little_helpers/__init__.py's _RELOAD_ORDER) and would
silently reset a plain global back to its default on the very next press.
Same pattern as lh_router's dev-mode flag.
"""

import nuke

_NODE_NAME = "LH_ViewerFlip"


def _flip_on():
    return getattr(nuke, "_lh_viewer_flip_on", False)


def _existing_node():
    return nuke.toNode(_NODE_NAME)


def _make_node():
    """Built fresh on each flip-on, deleted on flip-off (see
    toggle_viewer_flip) rather than left disabled in the script -- an
    input-process node is otherwise an orphan sitting in the graph with
    no reason to be there once the flip is off, and a stray leftover
    would confuse the next person who opens the script."""
    node = nuke.nodes.Mirror2(name=_NODE_NAME)
    node["flop"].setValue(True)  # Mirror2's actual knob names are flip (vertical) / flop (horizontal)
    node.setXYpos(-2000, -2000)  # tucked away -- never meant to be seen/edited
    node.setSelected(False)  # new nodes come back selected -- don't hijack the artist's current selection
    return node


def _apply_to_viewer(viewer, node):
    if node is not None:
        viewer["input_process_node"].setValue(node.fullName())
        viewer["input_process"].setValue(True)
    else:
        viewer["input_process"].setValue(False)


def _on_viewer_created():
    """nuke.addOnCreate(nodeClass='Viewer') callback, registered once from
    register() below -- picks up a Viewer created *while* the flip is
    already on, so it joins the mirror immediately instead of needing a
    second F2 press to catch up."""
    if not _flip_on():
        return
    node = _existing_node() or _make_node()
    _apply_to_viewer(nuke.thisNode(), node)


def register():
    """Idempotent enough to call repeatedly (register_menu() may run more
    than once a session) -- Nuke de-dupes addOnCreate on identical
    (callback, nodeClass, args) registrations."""
    nuke.addOnCreate(_on_viewer_created, nodeClass="Viewer")


def toggle_viewer_flip():
    """F2 -- mirrors every current Viewer horizontally, or clears it."""
    turning_on = not _flip_on()
    nuke._lh_viewer_flip_on = turning_on

    if turning_on:
        node = _existing_node() or _make_node()
        for viewer in nuke.allNodes("Viewer"):
            _apply_to_viewer(viewer, node)
        print("[Little Helpers] viewer flip ON -- all viewers mirrored horizontally")
    else:
        for viewer in nuke.allNodes("Viewer"):
            _apply_to_viewer(viewer, None)
        node = _existing_node()
        if node is not None:
            nuke.delete(node)
        print("[Little Helpers] viewer flip OFF")
