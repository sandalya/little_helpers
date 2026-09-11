"""
little_helpers.repath

Auto-repath on paste: when a layer-branch comp built for one shot gets
copy-pasted into another shot's script (Sashok's recurring workflow for
near-identical shots -- same light rig, same camera angles, so the comp
graph is reused wholesale), every Read node's file path still points at
the OLD shot's render folder. This detects that case from the pasted
selection and offers to repath every mismatched Read to the CURRENT
shot's latest version -- reusing the exact resolve/apply functions
Function 1 (layer_branch.build_layer_branch) and Function 2
(veriter.versions) already use. This module is glue over that code, not a
new engine.

Hooked into Ctrl+V itself (see __init__.py's register_menu, which
overrides Nuke's built-in Nuke/Edit/Paste command -- confirmed live via a
recursive nuke.menu() scan that Paste lives there, not under a plain
top-level "Edit" menu, same class of hidden-menu gotcha as the Shift+D
collision documented elsewhere in this project) rather than
nuke.addOnUserCreate: a multi-node paste fires addOnUserCreate once per
node, but Ctrl+V fires once, and Nuke has already selected exactly the
pasted nodes by the time our wrapper regains control -- so the whole
pasted batch is inspected as one group, with one popup, not N.
"""

import os
import re

import nuke

from .layer_branch import _TRAILING_SHOT_NUM_RE, _apply_read_sequence, _resolve_pass
from .veriter.versions import _is_live_read, _parse_read_file

# _TRAILING_SHOT_NUM_RE (see layer_branch.py) strips a layer folder's
# trailing "_<shot-number>" (bg_320 -> bg) -- confirmed live 2026-09-10 by
# a real WinError 3 on paste (sh320 -> sh370): a naive basename copy (old
# code here: layer_name = basename(old_layer_dir)) carries the OLD shot's
# number straight into the new shot's render root, where it doesn't exist.


def _find_matching_layer_dir(current_root, old_layer_name):
    """Given a layer folder name pasted in from another shot (e.g.
    "bg_320"), find the equivalent folder under this shot's render root
    (current_root). Strips a trailing "_<digits>" to get the
    shot-independent base name ("bg") and looks for a folder under
    current_root matching that base name -- exactly, or with any numeric
    suffix (covers "bg" alone too, for shows that don't suffix layer
    folders with the shot number at all). Falls back to the literal old
    name unchanged if nothing under current_root matches the base name
    but does match the old name verbatim (unusual, but cheaper to allow
    than to hard-fail on). Returns None if no folder under current_root
    plausibly corresponds to this layer."""
    m = _TRAILING_SHOT_NUM_RE.match(old_layer_name)
    base_name = m.group(1) if m else old_layer_name

    try:
        entries = os.listdir(current_root)
    except OSError:
        return None

    if base_name in entries:
        return base_name

    candidates = []
    for entry in entries:
        em = _TRAILING_SHOT_NUM_RE.match(entry)
        if em and em.group(1) == base_name:
            candidates.append(entry)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return None  # ambiguous -- caller reports this Read as skipped

    if old_layer_name in entries:
        return old_layer_name

    return None


def _rename_layer_in_text(text, old_layer_name, new_layer_name):
    """Case-insensitive substring replace of old_layer_name with
    new_layer_name.upper() inside text -- build_layer_branch's StickyNote
    labels are exactly layer_name.upper() ("BG_320"), so a paste carries
    the OLD shot's number in the branch label too, not just the Read
    paths. Case-insensitive match (label is uppercase, old_layer_name as
    parsed from a file path is lowercase) but the replacement is always
    uppercased, matching how build_layer_branch itself writes labels."""
    pattern = re.compile(re.escape(old_layer_name), re.IGNORECASE)
    return pattern.sub(new_layer_name.upper(), text)


def paste_and_maybe_repath():
    """Replacement command for Nuke's built-in Ctrl+V (see __init__.py's
    register_menu). Pastes exactly as Nuke's own Edit/Paste does, then
    inspects the resulting selection."""
    import nukescripts
    with nuke.lastHitGroup():
        nuke.nodePaste(nukescripts.cut_paste_file())
    maybe_offer_repath(nuke.selectedNodes())


def maybe_offer_repath(pasted_nodes):
    """Given the just-pasted node selection, look for two things and, if
    either is found, ask once (nuke.ask, per Sashok's call -- no custom
    HUD needed for a yes/no) before touching anything:

    - live Read nodes (feed something else in the graph -- see
      veriter._is_live_read) whose file path resolves to a layer_dir
      outside the CURRENT script's $FTRACK_RENDER_PATH, i.e. brought in
      from a different shot's branch. These get repathed to this shot's
      same layer/pass, latest version on disk.
    - disconnected history Read nodes that came along for the ride --
      per Sashok's call (2026-09-10), these are just deleted rather than
      repathed or reparented; he reopens history by hand if a shot
      actually needs it.

    Silently does nothing if $FTRACK_RENDER_PATH isn't set (no notion of
    "correct shot" to repath toward) or if nothing pasted looks like a
    layer-branch Read at all -- _parse_read_file returns None for
    anything that doesn't match the
    ".../<layer>/vNNN/<pass>_product.<frame>.<ext>" convention, so an
    ordinary same-shot paste, or pasting an unrelated reference Read,
    triggers no popup at all."""
    current_root = os.environ.get("FTRACK_RENDER_PATH")
    if not current_root:
        return

    reads = [n for n in pasted_nodes if n.Class() == "Read"]
    if not reads:
        return

    history = []
    mismatched = []  # (read, old_layer_dir, pass_name)
    for read in reads:
        parsed = _parse_read_file(read["file"].value())
        if parsed is None:
            continue
        layer_dir, _version, pass_name = parsed
        if not _is_live_read(read):
            history.append(read)
            continue
        if not layer_dir.startswith(current_root):
            mismatched.append((read, layer_dir, pass_name))

    stickies = [n for n in pasted_nodes if n.Class() == "StickyNote"]

    if not history and not mismatched:
        return

    lines = []
    if mismatched:
        old_roots = sorted({os.path.dirname(d) for _, d, _ in mismatched})
        lines.append(
            f"{len(mismatched)} Read(s) look like they're from another "
            f"shot ({', '.join(old_roots)})."
        )
    if history:
        lines.append(f"{len(history)} disconnected history Read(s) came along too.")
    lines.append(
        "Repath the mismatched Reads to this shot's latest renders"
        + (" and delete the history Reads" if history else "")
        + (", and relabel branch StickyNotes" if stickies else "")
        + "?"
    )

    if not nuke.ask("\n".join(lines)):
        return

    repathed, skipped = 0, []
    layer_renames = {}  # old_layer_name -> new_layer_name, for StickyNotes below
    for read, layer_dir, pass_name in mismatched:
        old_layer_name = os.path.basename(layer_dir)
        new_layer_name = _find_matching_layer_dir(current_root, old_layer_name)
        if new_layer_name is None:
            skipped.append(read.name())
            continue
        new_layer_dir = f"{current_root}/{new_layer_name}"
        try:
            version, seq = _resolve_pass(new_layer_dir, pass_name)
        except ValueError:
            skipped.append(read.name())
            continue
        _apply_read_sequence(read, pass_name, version, seq, new_layer_dir)
        repathed += 1
        layer_renames[old_layer_name] = new_layer_name

    for read in history:
        nuke.delete(read)

    relabeled = 0
    for sticky in stickies:
        label = sticky["label"].value()
        new_label = label
        for old_layer_name, new_layer_name in layer_renames.items():
            new_label = _rename_layer_in_text(new_label, old_layer_name, new_layer_name)
        if new_label != label:
            sticky["label"].setValue(new_label)
            relabeled += 1

    summary = (
        f"repath_on_paste: {repathed} Read(s) repathed, "
        f"{len(history)} history Read(s) deleted, "
        f"{relabeled} StickyNote(s) relabeled"
    )
    if skipped:
        summary += (
            f", {len(skipped)} skipped (no matching renders in this "
            f"shot: {', '.join(skipped)})"
        )
    print(summary)
