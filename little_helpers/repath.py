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

Hooked into Alt+V itself (rebound from the original Ctrl+V 2026-09-11, per
Sashok's ask -- see __init__.py's register_menu, which overrides Nuke's
built-in Nuke/Edit/Paste command -- confirmed live via a recursive
nuke.menu() scan that Paste lives there, not under a plain top-level
"Edit" menu, same class of hidden-menu gotcha as the Shift+D collision
documented elsewhere in this project) rather than nuke.addOnUserCreate: a
multi-node paste fires addOnUserCreate once per node, but this hotkey
fires once, and Nuke has already selected exactly the pasted nodes by the
time our wrapper regains control -- so the whole pasted batch is
inspected as one group, with one popup, not N.
"""

import os
import re

import nuke

from .layer_branch import (
    _apply_read_sequence,
    _find_layer_candidates,
    _resolve_pass,
)
from .veriter.versions import _is_live_read, _parse_read_file

# _find_layer_candidates (layer_branch.py) strips a layer folder's
# trailing "_<shot-number>" (bg_320 -> bg) -- confirmed live 2026-09-10 by
# a real WinError 3 on paste (sh320 -> sh370): a naive basename copy (old
# code here: layer_name = basename(old_layer_dir)) carries the OLD shot's
# number straight into the new shot's render root, where it doesn't exist.
# It also declines to guess when the current shot's render root has more
# than one folder matching the same base name (ambiguous -- e.g. sh320
# holding both "chars_320" and a stray "chars_340", confirmed live
# 2026-09-11) -- those go into the popup's needs_input rows below, each
# with a QComboBox pre-filtered to the actual candidates, instead of the
# old behaviour of silently lumping them in with "no match at all".


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
    """Bound to Alt+V (see __init__.py's register_menu), replacing Nuke's
    built-in Ctrl+V paste at the Edit/Paste menu path. Pastes exactly as
    Nuke's own Edit/Paste does, then inspects the resulting selection."""
    import nukescripts
    with nuke.lastHitGroup():
        nuke.nodePaste(nukescripts.cut_paste_file())
    maybe_offer_repath(nuke.selectedNodes())


def paste_plain():
    """Bound to plain Ctrl+V (see __init__.py's register_menu) -- restores
    Nuke's own paste behaviour with no repath check, lost when the Alt+V
    rebind (2026-09-12) took over the Edit/Paste menu path outright:
    removeItem there drops the native Ctrl+V binding for good, Nuke does
    not fall back to it on its own (confirmed live -- Ctrl+V did nothing
    after the rebind until this was added). Registered as its own
    separate menu command/hotkey, not folded into paste_and_maybe_repath,
    so a plain paste never runs the cross-shot check at all -- matches
    Nuke's stock Edit/@;Paste2 (Ctrl+Shift+V) sitting alongside Edit/Paste
    as its own untouched command."""
    import nukescripts
    with nuke.lastHitGroup():
        nuke.nodePaste(nukescripts.cut_paste_file())


def maybe_offer_repath(pasted_nodes):
    """Given the just-pasted node selection, look for two things and, if
    either is found, put up one dialog (repath_ui.ask_repath -- a custom
    PySide dialog replacing the old plain nuke.ask() text blob, see
    BACKLOG.md 2026-09-11) before touching anything:

    - live Read nodes (feed something else in the graph -- see
      veriter._is_live_read) whose file path resolves to a layer_dir
      outside the CURRENT script's $FTRACK_RENDER_PATH, i.e. brought in
      from a different shot's branch. Each is triaged by
      layer_branch._find_layer_candidates into "resolved" (single
      unambiguous match -- repathed straight away if the artist confirms)
      or "needs_input" (ambiguous same-base-name candidates, or none at
      all -- the dialog shows one QComboBox per row, pre-filtered to the
      real candidates when there are any). Grouped by old_layer_name, not
      one row per Read: a layer-branch's 4 passes (lights/beauty/tech/
      crypto) share one layer_dir, so an ambiguous match applies to all of
      them identically -- one decision per layer, not per pass.
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
    resolved = []       # (read, old_layer_dir, pass_name, new_layer_name)
    needs_input_groups = {}  # old_layer_name -> {"candidates", "all_entries", "reads": [(read, layer_dir, pass_name), ...]}
    for read in reads:
        parsed = _parse_read_file(read["file"].value())
        if parsed is None:
            continue
        layer_dir, _version, pass_name = parsed
        if not _is_live_read(read):
            history.append(read)
            continue
        if layer_dir.startswith(current_root):
            continue
        old_layer_name = os.path.basename(layer_dir)
        # Grouped by old_layer_name, not one row per Read: a layer-branch's
        # 4 passes (lights/beauty/tech/crypto) all live under the same
        # layer_dir, so they share the exact same candidates/all_entries --
        # one dropdown decision per LAYER, not one per pass (confirmed by
        # Sashok 2026-09-11: a real chars_370 paste showed 4 near-identical
        # rows, one per pass, for what was really one ambiguous folder).
        if old_layer_name in needs_input_groups:
            needs_input_groups[old_layer_name]["reads"].append((read, layer_dir, pass_name))
            continue
        info = _find_layer_candidates(current_root, old_layer_name)
        if info["match"] is not None:
            resolved.append((read, layer_dir, pass_name, info["match"]))
        else:
            needs_input_groups[old_layer_name] = {
                "candidates": info["candidates"],
                "all_entries": info["all_entries"],
                "reads": [(read, layer_dir, pass_name)],
            }

    needs_input = [
        (old_layer_name, g["candidates"], g["all_entries"], g["reads"])
        for old_layer_name, g in needs_input_groups.items()
    ]

    stickies = [n for n in pasted_nodes if n.Class() == "StickyNote"]

    if not history and not resolved and not needs_input:
        return

    from .repath_ui import ask_repath
    proceed, picks = ask_repath(resolved, needs_input, history, stickies)
    if not proceed:
        return

    repathed, skipped = 0, []
    layer_renames = {}  # old_layer_name -> new_layer_name, for StickyNotes below

    def _apply(read, layer_dir, pass_name, new_layer_name):
        nonlocal repathed
        old_layer_name = os.path.basename(layer_dir)
        new_layer_dir = f"{current_root}/{new_layer_name}"
        try:
            version, seq = _resolve_pass(new_layer_dir, pass_name)
        except ValueError:
            skipped.append(read.name())
            return
        _apply_read_sequence(read, pass_name, version, seq, new_layer_dir)
        repathed += 1
        layer_renames[old_layer_name] = new_layer_name

    for read, layer_dir, pass_name, new_layer_name in resolved:
        _apply(read, layer_dir, pass_name, new_layer_name)

    for old_layer_name, _candidates, _all_entries, group_reads in needs_input:
        chosen = picks.get(old_layer_name)
        for read, layer_dir, pass_name in group_reads:
            if chosen is None:
                skipped.append(read.name())
                continue
            _apply(read, layer_dir, pass_name, chosen)

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
