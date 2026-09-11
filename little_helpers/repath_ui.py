"""
little_helpers.repath_ui

Modal confirm dialog for repath.py's paste-time popup (Ctrl+V) -- replaces
the old plain nuke.ask() text blob with a compact colour-coded summary
(green = will auto-repath, amber = a few same-base-name candidates to pick
from, red = no candidate at all in this shot) plus one QComboBox per row
that needs a human decision. See BACKLOG.md 2026-09-11: sh320's render
root held both "chars_320" and a stray "chars_340" on a real paste, and
the old code silently lumped that together with "no match at all" into
one Script Editor line -- no way to tell the two apart, let alone fix it,
without going to disk by hand.

First real modal QDialog in this project (the other HUDs -- hud.py,
layer_picker_ui.py, veriter/version_ui.py -- are all frameless
Qt.Tool popups that close on an outside click, deliberately not modal).
A Yes/Ні confirm with per-row pick state wants blocking exec_() and native
window chrome, not the click-away pattern those use.
"""

import os

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

_GREEN = "#7CC47F"
_RED = "#E2776C"
_AMBER = "#D7A94E"
_DIM = "#9B9EA3"

_STYLE = f"""
    QDialog {{ background-color: #2B2E31; }}
    QLabel {{ color: #E9E7E2; font-size: 12px; }}
    QLabel[role="ask"] {{ font-size: 13px; }}
    QLabel[role="section"] {{ color: {_AMBER}; font-weight: 600;
        font-size: 11px; }}
    QLabel[role="rowhead"] {{ font-family: Consolas; font-weight: 600; }}
    QLabel[role="rowpath"] {{ font-family: Consolas; color: {_DIM}; font-size: 11px; }}
    QLabel[role="reason"] {{ color: {_DIM}; font-size: 11px; }}
    QLabel[role="footnote"] {{ color: {_DIM}; font-size: 11px; }}
    QFrame[role="row_ambiguous"] {{ background-color: rgba(215, 169, 78, 0.13);
        border: 1px solid rgba(215, 169, 78, 0.4); border-radius: 5px; }}
    QFrame[role="row_unmatched"] {{ background-color: rgba(226, 119, 108, 0.13);
        border: 1px solid rgba(226, 119, 108, 0.38); border-radius: 5px; }}
    QFrame[role="divider"] {{ background-color: #414448; max-height: 1px; }}
    QComboBox {{ background-color: #35383C; color: #E9E7E2;
        border: 1px solid #46494E; border-radius: 4px; padding: 3px 6px;
        font-family: Consolas; font-size: 11px; }}
    QPushButton {{ border-radius: 4px; padding: 7px 16px; font-weight: 600; }}
    QPushButton[role="yes"] {{ background-color: rgba(124, 196, 127, 0.16);
        border: 1px solid rgba(124, 196, 127, 0.4); color: #7CC47F; }}
    QPushButton[role="yes"]:hover {{ background-color: rgba(124, 196, 127, 0.28); }}
    QPushButton[role="no"] {{ background-color: #35383C;
        border: 1px solid rgba(226, 119, 108, 0.38); color: #E2776C; }}
    QPushButton[role="no"]:hover {{ background-color: rgba(226, 119, 108, 0.16); }}
"""


def _hline():
    line = QtWidgets.QFrame()
    line.setProperty("role", "divider")
    line.setFixedHeight(1)
    return line


class _RepathDialog(QtWidgets.QDialog):
    def __init__(self, resolved, needs_input, history, stickies, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вставка з іншого шоту")
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(440)
        self._combos = {}  # read.name() -> QComboBox

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        if needs_input:
            plural = "шлях" if len(needs_input) == 1 else "шляхи"
            section = QtWidgets.QLabel(
                f"{len(needs_input)} {plural} не вдалось визначити автоматично"
            )
            section.setProperty("role", "section")
            layout.addWidget(section)

            for read, old_dir, pass_name, candidates, all_entries in needs_input:
                row = QtWidgets.QFrame()
                row.setProperty("role", "row_ambiguous" if candidates else "row_unmatched")
                row_layout = QtWidgets.QVBoxLayout(row)
                row_layout.setContentsMargins(10, 8, 10, 8)
                row_layout.setSpacing(4)

                head = QtWidgets.QLabel(f"{read.name()} · {pass_name}")
                head.setProperty("role", "rowhead")
                row_layout.addWidget(head)

                path_label = QtWidgets.QLabel(os.path.basename(old_dir) + "  →  ?")
                path_label.setProperty("role", "rowpath")
                row_layout.addWidget(path_label)

                reason = QtWidgets.QLabel(
                    f"{len(candidates)} схожих варіанти в цьому шоті"
                    if candidates else "жодного схожого шару в цьому шоті"
                )
                reason.setProperty("role", "reason")
                row_layout.addWidget(reason)

                pick_row = QtWidgets.QHBoxLayout()
                pick_row.addWidget(QtWidgets.QLabel("взяти з:"))
                combo = QtWidgets.QComboBox()
                combo.addItem("— не чіпати —", None)
                for opt in (candidates or all_entries):
                    combo.addItem(opt, opt)
                pick_row.addWidget(combo, 1)
                row_layout.addLayout(pick_row)

                self._combos[read.name()] = combo
                layout.addWidget(row)

            layout.addWidget(_hline())

        extra_clauses = []
        if history:
            extra_clauses.append(f"{len(history)} відключених history Read буде видалено")
        if stickies:
            extra_clauses.append("StickyNote-лейбли шарів буде оновлено")

        if resolved:
            ask = QtWidgets.QLabel()
            ask.setProperty("role", "ask")
            ask.setTextFormat(QtCore.Qt.RichText)
            prefix = "Інші" if needs_input else "Замінити"
            ask.setText(
                f'{prefix} <span style="color:{_GREEN}; font-weight:600;">'
                f'{len(resolved)}</span> exr шляхів під поточний шот?'
            )
            layout.addWidget(ask)
        elif extra_clauses:
            # nothing auto-resolved, but history/sticky work is still on offer
            ask = QtWidgets.QLabel("Виконати ці дії?")
            ask.setProperty("role", "ask")
            layout.addWidget(ask)

        if needs_input:
            footnote = QtWidgets.QLabel("Рядки без вибору вище залишаться як є.")
            footnote.setProperty("role", "footnote")
            layout.addWidget(footnote)

        if extra_clauses:
            clauses_label = QtWidgets.QLabel("+ " + "; ".join(extra_clauses))
            clauses_label.setProperty("role", "footnote")
            layout.addWidget(clauses_label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        no_btn = QtWidgets.QPushButton("✕  Ні")
        no_btn.setProperty("role", "no")
        no_btn.clicked.connect(self.reject)
        yes_btn = QtWidgets.QPushButton("✓  Так")
        yes_btn.setProperty("role", "yes")
        yes_btn.setDefault(True)
        yes_btn.clicked.connect(self.accept)
        btn_row.addWidget(no_btn)
        btn_row.addWidget(yes_btn)
        layout.addLayout(btn_row)

    def picks(self):
        return {name: data for name, combo in self._combos.items()
                if (data := combo.currentData()) is not None}


def ask_repath(resolved, needs_input, history, stickies):
    """Modal replacement for repath.py's old nuke.ask() summary line.

    resolved: [(read, old_layer_dir, pass_name, new_layer_name), ...] --
      single unambiguous match (layer_branch._find_layer_candidates),
      auto-repathed if the artist confirms.
    needs_input: [(read, old_layer_dir, pass_name, candidates, all_entries), ...]
      -- one QComboBox per row, pre-filtered to `candidates` when there are
      same-base-name options, falling back to the shot's full render root
      (`all_entries`) when there isn't even that.
    history: disconnected Read nodes riding along (shown as a footnote,
      same delete-on-confirm behaviour as before).
    stickies: StickyNote nodes that would get relabelled (footnote only).

    Returns (proceed, picks). proceed is False if the artist hit Ні or
    closed the dialog -- picks is {} in that case. Otherwise picks maps
    read.name() -> the layer folder name chosen in that row's combo, for
    every needs_input row where the artist picked something other than
    "не чіпати" (rows left on that default are the caller's to treat as
    skipped, same as an unresolved match always has been)."""
    dlg = _RepathDialog(resolved, needs_input, history, stickies)
    proceed = dlg.exec_() == QtWidgets.QDialog.Accepted
    return proceed, (dlg.picks() if proceed else {})
