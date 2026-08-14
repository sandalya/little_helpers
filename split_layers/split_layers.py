import nuke

# The pipeline's Split Layers is the subpackage pl_scripts.split_layers
# (pl_scripts lives at the root of the studio's NUKE_PATH entry, e.g.
# C:/Users/Admin/Documents/plarium-nuke-<version>/pl_scripts/split_layers)
# -- confirmed against menu.py's own "Plarium" menu registration:
# plarium_menu.addCommand("Split Layers", pl_scripts.split_layers.main).
# main/data_collect/SplitLayers (the UI + layer-collection side) live
# directly in that package's __init__.py -- reused as-is below.
from pl_scripts import split_layers as _canonical

# nuke_actions.py here is OUR OWN, not the pipeline's -- unlike the UI/
# layer-collection side, node-graph spacing here is a deliberate,
# long-standing divergence (custom breathing room between forked shuffle
# branches and merge steps, per Sashok's ask -- see the constants' own
# comments), not something canonical's version reproduces. Confirmed live
# (screenshot comparison) that canonical's spacing doesn't match what's
# wanted here, so this one piece stays a local copy on purpose.
from . import nuke_actions

# Always-technical layers from Function 1's init template (rgba, position/
# depth/motion-vector/matte utility passes) -- never candidates for
# per-object split, so left out of the Input list. Per Sashok's ask.
_TECHNICAL_LAYERS = {'rgba', 'mask', 'depth', 'Zg', 'Pg', 'mv'}


def main():
    node = None
    try:
        node = nuke.selectedNode()
    except ValueError as err:
        print(err)
        nuke.message('no node selected')
    if not node:
        return
    data = _canonical.data_collect(node)
    data['layers'] = [l for l in data['layers'] if l not in _TECHNICAL_LAYERS]
    main.panel = _canonical.SplitLayers(data, nuke_actions.split_explicit, nuke_actions.split_implicit)
    main.panel.show()
