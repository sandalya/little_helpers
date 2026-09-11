"""
little_helpers.veriter.versions

Function 2 logic (Shift+E): jump-to-latest / step version up / step version
down on whatever Read node(s) are selected, each resolved independently
against its own (layer, pass) -- same per-pass-independent rule as
layer_branch.build_layer_branch. No shared "current branch" detection here
(that was the fuller Function 2 scope from docs/NUKE_COMP_LAYER_ASSEMBLY.md);
this only ever touches nodes the artist has actually selected.
"""

import os
import re

import nuke

from ..layer_branch import (
    _VERSION_DIR_RE,
    _apply_read_sequence,
    _available_versions,
    _collapse_sequence,
    _find_matching_layer_dir,
    _read_node_name,
    _resolve_pass,
)
from ..nuke_utils import nodes_in_view

_READ_PATH_RE = re.compile(
    r"^(?P<layer_dir>.+)/(?P<version>v\d+)/(?P<pass_name>\w+)_product\.",
    re.IGNORECASE,
)


def _parse_read_file(file_value):
    """Pull (layer_dir, version, pass_name) back out of a Read node's
    current file path, per the convention build_layer_branch writes
    (.../<layer>/<version>/<pass>_product.<frame-token>.<ext>). Not tied
    to _LAYER_BRANCH_PASSES -- matches whatever pass name actually
    precedes "_product.", so real production paths and hand-edited ones
    parse too, regardless of %04d vs #### frame-token style. Returns None
    if file_value doesn't match the convention at all."""
    m = _READ_PATH_RE.match(file_value)
    if not m:
        return None
    return m.group("layer_dir"), m.group("version"), m.group("pass_name")


_HISTORY_COUNTS = {"lights": 1, "beauty": 5}  # .get(pass_name, 0) -- 0
# (tech/crypto, or anything unrecognized) means "no history row for this
# pass". Matches the row of disconnected old-version Read nodes Sashok
# already builds by hand next to a live branch (confirmed on sh320/bg:
# 5 old beauty Reads, 1 old lights Read, none for tech/crypto).

# Reload-safe -- __init__.py's reload_all() re-runs this module's top
# level on every hotkey press (by design, see its docstring), so a plain
# `_HISTORY_ENABLED = True` here would silently reset the artist's
# checkbox choice back to on every time. Controls the
# "History" checkbox in version_ui._VersionHUD: True keeps
# _sync_history_reads running on every bump (original always-on behavior);
# False stops new history rows from being created (see bump_selected_reads)
# and, via _set_history_enabled, removes any that already exist.
if '_HISTORY_ENABLED' not in globals():
    _HISTORY_ENABLED = True

_HISTORY_SPACING = 110  # px between history-node slots, cosmetic only --
# splits the difference between the two spacings actually observed on disk
# (a hand-built history lights Read sat -116px from its live Read, a
# history beauty Read -108/-109px from its live Read). Safe to retune:
# these are disconnected reference nodes, moving them changes nothing.

_HISTORY_TILE_COLOR = 0x2E3B4EFF  # muted blue-gray -- distinguishes a
# history node from a live Read (default tile_color) at a glance, but
# applied only when that node's own sequence has no missing frames --
# the orange missing-frames flag _apply_read_sequence sets takes priority.


def _is_live_read(read):
    """True if read feeds something other than a Viewer. A plain
    node.dependent() check isn't enough on its own -- confirmed live:
    Read7 (a beauty history Read, tile_color already the history-node
    gray, postage_stamp already off) was still reported as "live" and got
    flagged/bumped, because Sashok had it plugged into a Viewer for visual
    comparison -- exactly the normal, expected use of a history Read.
    Viewer connections don't make a Read part of the actual comp, so they
    don't count here."""
    return any(d.Class() != "Viewer" for d in read.dependent())


def _working_read_nodes():
    """Read nodes version-stepping operates on: the current selection if
    there is one, else every Read node visible in the current Node Graph
    viewport (see nuke_utils.nodes_in_view) -- framing the view on a
    branch becomes an implicit "work on this" the same way explicitly
    selecting nodes does, per Sashok's ask. Further filtering
    (_is_live_read, the file-path convention) stays on the callers, same
    as it already was for an explicit selection."""
    selected = nuke.selectedNodes()
    if selected:
        return [n for n in selected if n.Class() == "Read"]
    try:
        return nodes_in_view("Read")
    except Exception as e:
        print(f"_working_read_nodes: nodes-in-view fallback failed -- {e}")
        return []


def _history_candidates(live_read, layer_dir, pass_name):
    """Read nodes elsewhere in the script that show the same (layer_dir,
    pass_name) as live_read but aren't it and have nothing downstream --
    i.e. the orphaned history/comparison Reads artists already build by
    hand (docs/NUKE_COMP_LAYER_ASSEMBLY.md: 'old versions are not
    deleted'). Deliberately NOT name-based -- Nuke's auto-numbered
    Read78/Read77 etc. carry no semantic meaning, only file path + graph
    topology do. A node counts as orphaned iff _is_live_read() is False --
    the same thing you'd check by eye to tell a live Read from a history
    one. Sorted by descending xpos so index 0 is closest to live_read
    (highest version-below-current slot)."""
    candidates = []
    for n in nuke.allNodes("Read"):
        if n is live_read:
            continue
        parsed = _parse_read_file(n["file"].value())
        if parsed is None:
            continue
        n_layer_dir, _n_version, n_pass_name = parsed
        if n_layer_dir != layer_dir or n_pass_name != pass_name:
            continue
        if _is_live_read(n):
            continue
        candidates.append(n)
    candidates.sort(key=lambda n: -n.xpos())
    return candidates


def _sync_history_reads(live_read, layer_dir, pass_name, current_num):
    """Called after a successful version bump on a beauty/lights live Read
    (see _HISTORY_COUNTS) to keep its row of old-version Read nodes in
    sync. _bump_read_version mutates live_read's own knobs in place rather
    than creating a new node, so there's no stored record of "what used to
    be live" to diff against -- every call re-derives the desired version
    list from disk instead of trying to track it. Reuses existing
    orphaned Reads first (adopting hand-built ones the first time this
    ever runs on a branch), creates new Read nodes only for any shortfall,
    and never deletes a node even if more orphans exist than currently
    wanted -- deletion needs its own explicit confirmation, out of scope
    here."""
    wanted = _HISTORY_COUNTS.get(pass_name, 0)
    if wanted <= 0:
        return

    versions = _available_versions(layer_dir, pass_name)  # ascending
    below = [v for v in versions if v[0] < current_num]
    targets = below[-wanted:]  # top `wanted` versions strictly below current
    targets.reverse()          # descending: targets[0] = closest-to-live

    candidates = _history_candidates(live_read, layer_dir, pass_name)

    for rank, (_version_num, version_name) in enumerate(targets, start=1):
        node = candidates[rank - 1] if rank - 1 < len(candidates) else \
            nuke.createNode("Read", inpanel=False)

        node.setXYpos(live_read.xpos() - rank * _HISTORY_SPACING, live_read.ypos())

        seq = _collapse_sequence(f"{layer_dir}/{version_name}", pass_name)
        _apply_read_sequence(node, pass_name, version_name, seq, layer_dir)
        if not seq["missing"]:
            node["tile_color"].setValue(_HISTORY_TILE_COLOR)


def _set_history_enabled(enabled):
    """Backing function for version_ui._VersionHUD's "History" checkbox.
    Applies immediately to whatever _working_read_nodes() currently
    resolves to (selection, or nodes-in-view fallback), same working set
    the bump buttons use -- turning the checkbox on/off is itself the
    action, not just a setting for the next bump. Sets the
    _HISTORY_ENABLED flag (gates future bumps in bump_selected_reads)
    either way."""
    global _HISTORY_ENABLED
    _HISTORY_ENABLED = enabled

    reads = [n for n in _working_read_nodes() if _is_live_read(n)]
    touched = 0
    for read in reads:
        parsed = _parse_read_file(read["file"].value())
        if parsed is None:
            continue
        layer_dir, current_version, pass_name = parsed
        if _HISTORY_COUNTS.get(pass_name, 0) <= 0:
            continue  # tech/crypto/unrecognized -- no history row either way
        touched += 1
        if enabled:
            current_num = int(_VERSION_DIR_RE.match(current_version).group(1))
            _sync_history_reads(read, layer_dir, pass_name, current_num)
        else:
            for node in _history_candidates(read, layer_dir, pass_name):
                nuke.delete(node)

    print(f"_set_history_enabled({enabled}): applied to {touched} live Read(s) "
          f"with a history-eligible pass")


def _bump_read_version(read, direction):
    """direction: "latest" | "up" | "down". Returns (status, detail,
    parsed) where status is "updated" or "skipped", and parsed is
    (layer_dir, pass_name, target_num) on "updated" else None -- handed
    back so the caller can sync history Reads (see _sync_history_reads)
    without re-parsing the now-mutated file knob."""
    file_value = read["file"].value()
    parsed = _parse_read_file(file_value)
    if parsed is None:
        return "skipped", "unrecognized path", None
    layer_dir, current_version, pass_name = parsed

    versions = _available_versions(layer_dir, pass_name)
    if not versions:
        return "skipped", "no versions found on disk", None

    current_num = int(_VERSION_DIR_RE.match(current_version).group(1))
    old_first, old_last = read["first"].value(), read["last"].value()
    root = nuke.root()
    root_first, root_last = root.firstFrame(), root.lastFrame()

    if direction == "latest":
        target_num, target_vname = versions[-1]
        if target_num == current_num:
            # Same version folder can still gain frames after this Read was
            # set (e.g. one test frame rendered first, the full shot
            # rendered later into that same vNNN) -- re-check the on-disk
            # range before skipping just because the version number didn't
            # move (confirmed live on sh320/bg: v008 stuck at 1001-1001
            # after the shot finished rendering to 1001-1029 in v008).
            #
            # That disk-diff alone isn't enough on its own: it only catches
            # a range that changed since this Read was last set, not a
            # range that was ALREADY short of the shot the whole time (a
            # Read built while only one frame existed, whose disk range
            # then happens to match what's on disk right now because
            # nothing rendered since -- same sh320/bg Read8 case, seen
            # stuck at 1001-1001 against a 1001-1029 shot). So also skip
            # only if the Read's current range actually covers root's
            # frame range -- same "incomplete" question _read_status
            # already answers for the HUD's status panel, asked here too
            # so a short Read never reads as "already at latest" just
            # because the on-disk bytes didn't move this time.
            seq = _collapse_sequence(f"{layer_dir}/{target_vname}", pass_name)
            unchanged = seq and seq["first"] == old_first and seq["last"] == old_last
            incomplete = old_first > root_first or old_last < root_last
            if not seq or (unchanged and not incomplete):
                return "skipped", "already at latest", None
    elif direction == "up":
        higher = [(n, v) for n, v in versions if n > current_num]
        if not higher:
            return "skipped", "no higher version available", None
        target_num, target_vname = higher[0]
    elif direction == "down":
        lower = [(n, v) for n, v in versions if n < current_num]
        if not lower:
            return "skipped", "no lower version available", None
        target_num, target_vname = lower[-1]
    else:
        raise ValueError(f"unknown direction {direction!r}")

    seq = _collapse_sequence(f"{layer_dir}/{target_vname}", pass_name)
    _apply_read_sequence(read, pass_name, target_vname, seq, layer_dir)
    if pass_name == "beauty":
        read["postage_stamp"].setValue(True)  # this is the live main Read,
        # not a history one -- see _apply_read_sequence's postage_stamp note
    if target_num == current_num:
        detail = f"{current_version} range refreshed ({int(old_first)}-{int(old_last)} -> {seq['first']}-{seq['last']})"
    else:
        detail = f"{current_version} -> {target_vname}"
    return "updated", detail, (layer_dir, pass_name, target_num)


def _cross_shot_layer(read):
    """If read's file path parses to the layer-branch convention and its
    layer_dir resolves outside the current shot's $FTRACK_RENDER_PATH,
    return (layer_dir, pass_name, old_layer_name) -- else None. Same
    mismatch check repath.maybe_offer_repath already runs on a fresh
    Alt+V paste, reused here so Shift+E also catches a cross-shot Read
    that slipped past that check (typed by hand, or pasted before this
    repath tooling existed). Silently returns None (no notion of "the
    right shot") if $FTRACK_RENDER_PATH isn't set."""
    current_root = os.environ.get("FTRACK_RENDER_PATH")
    if not current_root:
        return None
    parsed = _parse_read_file(read["file"].value())
    if parsed is None:
        return None
    layer_dir, _version, pass_name = parsed
    if layer_dir.startswith(current_root):
        return None
    return layer_dir, pass_name, os.path.basename(layer_dir)


def _maybe_repath_cross_shot_reads(reads):
    """Given the working set bump_selected_reads is about to act on, find
    any live-and-in-scope Reads that look like they're from another shot
    (see _cross_shot_layer), ask once (nuke.ask, same as repath.py's
    paste-time popup -- one popup for the batch, not one per Read), and
    repath whatever the artist confirms to this shot's latest version of
    the same layer/pass. A Read that stays mismatched afterward (artist
    said no, or no matching layer folder found -- see
    _find_matching_layer_dir's ambiguous-match case) is left alone and
    falls through to the normal per-pass version bump below, same as
    before this check existed."""
    current_root = os.environ.get("FTRACK_RENDER_PATH")
    if not current_root:
        return

    mismatched = []  # (read, layer_dir, pass_name, old_layer_name)
    for read in reads:
        info = _cross_shot_layer(read)
        if info is not None:
            mismatched.append((read,) + info)
    if not mismatched:
        return

    old_roots = sorted({os.path.dirname(d) for _, d, _, _ in mismatched})
    if not nuke.ask(
        f"{len(mismatched)} selected Read(s) look like they're from "
        f"another shot ({', '.join(old_roots)}).\n"
        "Repath to this shot's latest renders before changing version?"
    ):
        return

    for read, layer_dir, pass_name, old_layer_name in mismatched:
        new_layer_name = _find_matching_layer_dir(current_root, old_layer_name)
        if new_layer_name is None:
            print(f"_maybe_repath_cross_shot_reads: {read.name()} skipped -- "
                  f"no unambiguous match for '{old_layer_name}' under {current_root}")
            continue
        new_layer_dir = f"{current_root}/{new_layer_name}"
        try:
            version, seq = _resolve_pass(new_layer_dir, pass_name)
        except ValueError as e:
            print(f"_maybe_repath_cross_shot_reads: {read.name()} skipped -- {e}")
            continue
        _apply_read_sequence(read, pass_name, version, seq, new_layer_dir)
        print(f"_maybe_repath_cross_shot_reads: {read.name()} repathed "
              f"{old_layer_name} -> {new_layer_name} ({version})")


def _maybe_rename_read(read):
    """Renames read to the READ_<LAYER>_<PASS> convention (see
    layer_branch._read_node_name) if its file matches the layer-branch
    path convention and its current name isn't already that -- catches
    Reads built before this naming convention existed (or by hand), so
    running Shift+E on an old Read fixes its name along with its version.
    No-op for anything _parse_read_file can't make sense of."""
    parsed = _parse_read_file(read["file"].value())
    if parsed is None:
        return
    layer_dir, _version, pass_name = parsed
    target = _read_node_name(layer_dir, pass_name)
    if read.name() != target:
        old_name = read.name()
        read.setName(target, uncollide=True)
        print(f"_maybe_rename_read: {old_name} -> {read.name()}")


def bump_selected_reads(direction):
    """Triggered by a version_ui._VersionHUD button. Acts on
    _working_read_nodes() (current selection, or everything visible in the
    Node Graph viewport if nothing's selected), filtered to Read nodes,
    each resolved independently -- prints a one-line summary to the Script
    Editor (same feedback channel used elsewhere). Also keeps each bumped
    beauty/lights Read's history row in sync (see _sync_history_reads),
    and restores the original graph selection afterward:
    nuke.createNode() (used there when a new history node is needed)
    resets the selection as a side effect, which would otherwise leave the
    artist's selection pointing at a random history Read instead of what
    they actually picked -- and _VersionHUD's status refresh reads
    _working_read_nodes() right after this returns, so a wrong selection
    there would report on the wrong nodes too.

    The not-live skip (see _is_live_read) only applies to the nodes-in-view
    fallback (nothing explicitly selected) -- Sashok's ask: an explicit
    selection is itself the artist saying "act on this," even if it's a
    disconnected history Read, so it should always bump. The fallback
    still needs the guard since "everything visible in the viewport"
    routinely includes history Reads sitting right next to their live
    sibling that the artist never meant to touch."""
    original_selection = nuke.selectedNodes()
    explicit_selection = bool(original_selection)
    reads = _working_read_nodes()

    # In-scope for the cross-shot check: same set the loop below will
    # actually touch (an unselected, not-live nodes-in-view Read is
    # skipped either way, so asking about it would be noise).
    in_scope = [r for r in reads if explicit_selection or _is_live_read(r)]
    _maybe_repath_cross_shot_reads(in_scope)

    updated = 0
    skipped = 0
    for read in reads:
        live = _is_live_read(read)
        if not live and not explicit_selection:
            # Not live and not explicitly picked -- nothing downstream, so
            # this is itself a history/reference Read (docs/
            # NUKE_COMP_LAYER_ASSEMBLY.md's "old versions kept, not
            # deleted" pattern), and it only ended up in the working set
            # via the nodes-in-view fallback. Skip outright.
            skipped += 1
            print(f"bump_selected_reads({direction!r}): {read.name()} skipped -- "
                  f"not live (no downstream connections, looks like a history Read)")
            continue
        status, detail, parsed = _bump_read_version(read, direction)
        if status == "updated":
            updated += 1
            layer_dir, pass_name, target_num = parsed
            # History-row sync stays gated on liveness regardless of how
            # the node entered the working set -- syncing a disconnected
            # Read would make IT a "live" head and build it its own
            # history row too, cascading extra nodes (confirmed live: a
            # co-selected old history Read spun off its own history
            # chain, back when this gate didn't exist at all).
            if live and _HISTORY_COUNTS.get(pass_name, 0) > 0 and _HISTORY_ENABLED:
                _sync_history_reads(read, layer_dir, pass_name, target_num)
        else:
            skipped += 1
        print(f"bump_selected_reads({direction!r}): {read.name()} {status} -- {detail}")
        _maybe_rename_read(read)
    print(f"bump_selected_reads({direction!r}): {updated} updated, {skipped} skipped")

    for n in nuke.selectedNodes():
        n.setSelected(False)
    for n in original_selection:
        n.setSelected(True)


def _read_status(read):
    """Outdated / missing-frames / shot-range-incomplete flags for a
    single Read, reusing the same convention-parsing + disk scan
    _bump_read_version already does. Returns None for Read nodes that
    don't match the layer-branch file convention at all.

    "incomplete" is the check _collapse_sequence's missing-frames list
    can't do on its own: a Read whose file knob only ever pointed at one
    rendered frame (first == last, no internal gap possible) still might
    cover only 1 of the shot's N frames -- confirmed live on sh320/bg's
    beauty Read (v008, first=last=1001 against a 1001-1029 shot range).

    "outdated" is only ever checked for the beauty pass -- per
    docs/NUKE_COMP_LAYER_ASSEMBLY.md the 4 passes version independently
    and are routinely NOT lock-step on purpose (e.g. beauty re-rendered
    for a fix while lights/tech/crypto sit untouched), so flagging
    lights/tech/crypto as "outdated" whenever beauty moves ahead is just
    noise, not a real problem -- confirmed by Sashok live (a lights Read
    a version behind its branch's beauty got flagged and shouldn't have
    been)."""
    parsed = _parse_read_file(read["file"].value())
    if parsed is None:
        return None
    layer_dir, current_version, pass_name = parsed
    current_num = int(_VERSION_DIR_RE.match(current_version).group(1))

    outdated = False
    latest_vname = current_version
    if pass_name == "beauty":
        versions = _available_versions(layer_dir, pass_name)
        latest_num, latest_vname = versions[-1] if versions else (current_num, current_version)
        outdated = latest_num > current_num

    seq = _collapse_sequence(f"{layer_dir}/{current_version}", pass_name)
    root = nuke.root()
    root_first, root_last = root.firstFrame(), root.lastFrame()

    return {
        "pass_name": pass_name,
        "current_version": current_version,
        "latest_version": latest_vname,
        "outdated": outdated,
        "missing": seq["missing"] if seq else [],
        "incomplete": bool(seq) and (seq["first"] > root_first or seq["last"] < root_last),
        "seq": seq,
        "root_range": (root_first, root_last),
    }
