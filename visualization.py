"""
Visualization module for Fault Trees and Event Trees.

Uses the graphviz Python library to generate tree diagrams.
Gate symbols are drawn with PyQt6 QPainter for standard FTA shapes:
  - AND gate: flat bottom, dome/curved top
  - OR gate: curved top, curved/pointed bottom

Requires the 'graphviz' system package (apt install graphviz) in
addition to the Python library (pip install graphviz).
"""

import os
import sys
import tempfile

import graphviz

BUNDLED_GRAPHVIZ_BIN = None
_DOT_PATH = None

def _setup_bundled_graphviz():
    global BUNDLED_GRAPHVIZ_BIN, _DOT_PATH
    import shutil

    dot = shutil.which("dot")
    if dot:
        _DOT_PATH = dot

    if not getattr(sys, 'frozen', False):
        return

    base = sys._MEIPASS
    gv_bin = os.path.join(base, 'graphviz_bin')

    if not os.path.isdir(gv_bin):
        exe_dir = os.path.dirname(sys.executable)
        for candidate in [
            os.path.join(exe_dir, '_internal', 'graphviz_bin'),
            os.path.join(exe_dir, 'graphviz_bin'),
        ]:
            if os.path.isdir(candidate):
                gv_bin = candidate
                break

    if not os.path.isdir(gv_bin):
        return

    BUNDLED_GRAPHVIZ_BIN = gv_bin
    os.environ['PATH'] = gv_bin + os.pathsep + os.environ.get('PATH', '')
    os.environ['GVBINDIR'] = gv_bin

    if sys.platform == 'win32' and hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(gv_bin)
        except OSError:
            pass

    dot_name = "dot.exe" if sys.platform == "win32" else "dot"
    bundled_dot = os.path.join(gv_bin, dot_name)
    if os.path.isfile(bundled_dot):
        _DOT_PATH = bundled_dot

_setup_bundled_graphviz()


def _render_dot(dot_graph, output_path):
    """Render a graphviz.Digraph by calling dot directly.

    The DOT source is fed to ``dot`` over stdin and the rendered image is
    read back from stdout, so Graphviz never has to open a file path itself.
    This avoids a known Graphviz-on-Windows failure where a temp/output path
    containing non-ASCII (e.g. Turkish) characters cannot be opened.
    On error we raise with Graphviz's stderr instead of failing silently,
    so the GUI can show the real reason.
    """
    import subprocess
    fmt = dot_graph.format or 'png'
    out_file = output_path + "." + fmt

    dot_exe = _DOT_PATH
    if not dot_exe:
        # No explicit dot binary found: fall back to the graphviz Python API.
        dot_graph.render(output_path, cleanup=True)
        return

    env = os.environ.copy()
    if BUNDLED_GRAPHVIZ_BIN:
        env['PATH'] = BUNDLED_GRAPHVIZ_BIN + os.pathsep + env.get('PATH', '')
        env['GVBINDIR'] = BUNDLED_GRAPHVIZ_BIN

    result = subprocess.run(
        [dot_exe, f"-T{fmt}"],
        input=dot_graph.source.encode("utf-8"),
        capture_output=True, timeout=30, env=env,
        cwd=BUNDLED_GRAPHVIZ_BIN if BUNDLED_GRAPHVIZ_BIN else None,
    )
    if result.returncode != 0 or not result.stdout:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"Graphviz dot basarisiz (kod {result.returncode}): {stderr}"
        )

    # Python yazar; dosya yolu Turkce karakter icerse bile sorun olmaz.
    with open(out_file, "wb") as f:
        f.write(result.stdout)

from models import BasicEvent, EventTree, FaultTree, GateType, SPNode


def _create_gate_png(gate_type: GateType, fill_color: str, name: str,
                     prob_lines: list[str], output_path: str,
                     width: int = 170, height: int = 140,
                     vote_k: int = 0, vote_n: int = 0):
    """Create a standard FTA gate symbol as PNG using PyQt6 QPainter."""
    from PyQt6.QtGui import QImage, QPainter, QPainterPath, QColor, QBrush, QPen, QFont
    from PyQt6.QtCore import Qt, QRectF

    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    shape_h = int(height * 0.52)
    m = 6

    path = QPainterPath()
    if gate_type == GateType.AND or gate_type == GateType.VOTE:
        path.moveTo(m, shape_h)
        path.lineTo(m, shape_h * 0.44)
        path.cubicTo(m, m, width - m, m, width - m, shape_h * 0.44)
        path.lineTo(width - m, shape_h)
        path.closeSubpath()
    else:
        mid_x = width / 2
        cs_y = shape_h * 0.28
        path.moveTo(m, cs_y)
        path.cubicTo(m, m, width - m, m, width - m, cs_y)
        path.cubicTo(width - m, shape_h * 0.72, mid_x + width * 0.10,
                     shape_h - 2, mid_x, shape_h)
        path.cubicTo(mid_x - width * 0.10, shape_h - 2, m,
                     shape_h * 0.72, m, cs_y)

    painter.setBrush(QBrush(QColor(fill_color)))
    painter.setPen(QPen(QColor("#444444"), 2.0))
    painter.drawPath(path)

    painter.setPen(QColor("white"))
    font = QFont("Sans", 14)
    font.setBold(True)
    painter.setFont(font)
    if gate_type == GateType.VOTE:
        type_text = f"{vote_k}/{vote_n}"
    elif gate_type == GateType.AND:
        type_text = "AND"
    else:
        type_text = "OR"
    painter.drawText(QRectF(0, 0, width, shape_h * 0.82),
                     Qt.AlignmentFlag.AlignCenter, type_text)

    y = shape_h + 4
    painter.setPen(QColor("#222222"))
    font = QFont("Sans", 9)
    font.setBold(True)
    painter.setFont(font)
    display_name = name if len(name) <= 24 else name[:22] + "…"
    painter.drawText(QRectF(2, y, width - 4, 16),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                     display_name)

    y += 17
    font.setBold(False)
    font.setPointSize(8)
    painter.setFont(font)
    painter.setPen(QColor("#444444"))
    for line in prob_lines:
        painter.drawText(QRectF(2, y, width - 4, 14),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         line)
        y += 14

    painter.end()
    img.save(output_path, "PNG")


def _create_event_png(name: str, prob_lines: list[str], fill_color: str,
                      output_path: str, width: int = 140, height: int = 140):
    """Create a basic event circle symbol as PNG using PyQt6 QPainter."""
    from PyQt6.QtGui import QImage, QPainter, QColor, QBrush, QPen, QFont
    from PyQt6.QtCore import Qt, QRectF

    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    m = 5
    circle_d = min(width, height) - 2 * m
    cx = (width - circle_d) / 2
    cy = m

    painter.setBrush(QBrush(QColor(fill_color)))
    painter.setPen(QPen(QColor("#444444"), 2.0))
    painter.drawEllipse(QRectF(cx, cy, circle_d, circle_d))

    painter.setPen(QColor("white"))
    font = QFont("Sans", 8)
    font.setBold(True)
    painter.setFont(font)
    display_name = name if len(name) <= 18 else name[:16] + "…"
    text_rect = QRectF(cx + 4, cy + circle_d * 0.15, circle_d - 8, circle_d * 0.35)
    painter.drawText(text_rect,
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter,
                     display_name)

    font.setBold(False)
    font.setPointSize(7)
    painter.setFont(font)
    line_y = cy + circle_d * 0.52
    for line in prob_lines:
        painter.drawText(QRectF(cx + 2, line_y, circle_d - 4, 14),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         line)
        line_y += 13

    painter.end()
    img.save(output_path, "PNG")


class FaultTreeVisualizer:
    """
    Generates a top-down fault tree diagram with standard FTA gate symbols.

    Gate shapes are drawn as PNG images using PyQt6 QPainter:
      - AND gate: flat bottom, dome top (blue/red)
      - OR gate: curved top, pointed bottom (orange/red)
    Basic events are drawn as circles (green).
    """

    GATE_COLORS = {
        GateType.AND: "#1565C0",
        GateType.OR: "#E65100",
        GateType.VOTE: "#6A1B9A",
    }
    TOP_COLOR = "#B71C1C"
    EVENT_COLOR = "#2E7D32"

    def __init__(self, fault_tree: FaultTree, results: dict | None = None):
        self.ft = fault_tree
        self.results = results or {}

    @staticmethod
    def _html_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _gate_html_label(self, gate, gid: str) -> str:
        is_top = (gid == self.ft.top_event_id)
        color = self.TOP_COLOR if is_top else self.GATE_COLORS.get(
            gate.gate_type, "#333333")
        if gate.gate_type == GateType.VOTE:
            type_text = f"{gate.vote_k}/{len(gate.children)}"
        elif gate.gate_type == GateType.AND:
            type_text = "AND"
        else:
            type_text = "OR"
        name = self._html_escape(gate.name)
        if len(name) > 24:
            name = name[:22] + "…"
        rows = (f'<TR><TD><FONT POINT-SIZE="14" COLOR="white">'
                f'<B>{type_text}</B></FONT></TD></TR>'
                f'<TR><TD><FONT POINT-SIZE="9" COLOR="#222222">'
                f'<B>{name}</B></FONT></TD></TR>')
        if gid in self.results:
            fp = self.results[gid]["failure_probability"]
            r = self.results[gid]["reliability"]
            rows += (f'<TR><TD><FONT POINT-SIZE="8" COLOR="#FFCCCC">'
                     f'F = {fp:.4e}</FONT></TD></TR>'
                     f'<TR><TD><FONT POINT-SIZE="8" COLOR="#CCFFCC">'
                     f'R = {r:.4e}</FONT></TD></TR>')
        return (f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2" '
                f'BGCOLOR="{color}">{rows}</TABLE>>')

    def _event_html_label(self, event) -> str:
        name = self._html_escape(event.name)
        if len(name) > 18:
            name = name[:16] + "…"
        r = event.get_reliability()
        fp = event.get_failure_probability()
        return (f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="1">'
                f'<TR><TD><FONT POINT-SIZE="9" COLOR="white">'
                f'<B>{name}</B></FONT></TD></TR>'
                f'<TR><TD><FONT POINT-SIZE="8" COLOR="white">'
                f'R = {r:.4e}</FONT></TD></TR>'
                f'<TR><TD><FONT POINT-SIZE="8" COLOR="white">'
                f'F = {fp:.4e}</FONT></TD></TR>'
                f'</TABLE>>')

    def render(self, output_path: str | None = None, fmt: str = "png") -> str:
        tmp_dir = tempfile.gettempdir()

        dot = graphviz.Digraph(
            "FaultTree",
            format=fmt,
            graph_attr={
                "rankdir": "TB",
                "splines": "polyline",
                "nodesep": "0.8",
                "ranksep": "0.9",
                "bgcolor": "#FAFAFA",
                "label": self.ft.name,
                "labelloc": "t",
                "fontsize": "18",
                "fontname": "Helvetica-Bold",
                "pad": "0.5",
            },
            edge_attr={
                "color": "#555555",
                "penwidth": "1.5",
                "arrowhead": "none",
            },
        )

        for gid, gate in self.ft.gates.items():
            is_top = (gid == self.ft.top_event_id)
            color = self.TOP_COLOR if is_top else self.GATE_COLORS.get(
                gate.gate_type, "#333333")
            shape = "invhouse" if gate.gate_type in (GateType.AND, GateType.VOTE) else "egg"
            dot.node(gid, label=self._gate_html_label(gate, gid),
                     shape=shape, style="filled,bold",
                     fillcolor=color, color="#444444", penwidth="2",
                     width="1.6", height="1.0")

        for eid, event in self.ft.basic_events.items():
            dot.node(eid, label=self._event_html_label(event),
                     shape="circle", style="filled",
                     fillcolor=self.EVENT_COLOR, color="#444444",
                     penwidth="2", width="1.2", height="1.2")

        for gid, gate in self.ft.gates.items():
            for child_id in gate.children:
                if child_id in self.ft.basic_events or child_id in self.ft.gates:
                    dot.edge(gid, child_id)

        if output_path is None:
            output_path = os.path.join(tmp_dir, "fault_tree_diagram")

        _render_dot(dot, output_path)
        return f"{output_path}.{fmt}"


class EventTreeVisualizer:
    """
    Generates a left-to-right event tree diagram.

    Layout:
      - Initiating event on the far left
      - Branch points as small nodes, one column per safety system
      - Upper branches = success (green), lower branches = failure (red)
      - Outcome boxes on the far right showing sequence, probability,
        and custom label if defined
    """

    def __init__(self, event_tree: EventTree,
                 outcomes: list[dict] | None = None,
                 basic_events: dict[str, BasicEvent] | None = None,
                 linked_fault_trees: dict | None = None):
        self.et = event_tree
        self.outcomes = outcomes or []
        self.basic_events = basic_events or {}
        self.linked_fault_trees = linked_fault_trees or {}

    def _get_branch_probs(self) -> list[tuple[str, float]]:
        # Reuse the engine's resolution so the diagram matches the results
        # table exactly (including fault-tree-linked branches).
        from engine import EventTreeEngine
        resolver = EventTreeEngine(self.et, self.basic_events,
                                   self.linked_fault_trees)
        return [(b.name, resolver.branch_success_probability(b))
                for b in self.et.branches]

    def render(self, output_path: str | None = None, fmt: str = "png") -> str:
        branch_probs = self._get_branch_probs()
        n = len(branch_probs)

        dot = graphviz.Digraph(
            "EventTree",
            format=fmt,
            graph_attr={
                "rankdir": "LR",
                "splines": "line",
                "nodesep": "0.15",
                "ranksep": "1.8",
                "bgcolor": "#FAFAFA",
                "label": self.et.name,
                "labelloc": "t",
                "fontsize": "18",
                "fontname": "Helvetica-Bold",
                "pad": "0.5",
            },
            node_attr={
                "fontname": "Helvetica",
                "fontsize": "9",
            },
            edge_attr={
                "fontname": "Helvetica",
                "fontsize": "8",
            },
        )

        if n == 0:
            dot.node("empty", "No branches defined", shape="box",
                     style="filled", fillcolor="#FFF9C4")
            if output_path is None:
                output_path = os.path.join(tempfile.gettempdir(),
                                           "event_tree_diagram")
            _render_dot(dot, output_path)
            return f"{output_path}.{fmt}"

        ie_label = (f"{self.et.initiating_event_name}\n"
                    f"Freq = {self.et.initiating_event_frequency:.2e}")
        dot.node("IE", ie_label, shape="box", style="filled,bold",
                 fillcolor="#FF8F00", fontcolor="white", width="1.5")

        with dot.subgraph() as s:
            s.attr(rank="same")
            for j, (bname, _) in enumerate(branch_probs):
                s.node(f"hdr_{j}", bname, shape="plaintext",
                       fontsize="11", fontname="Helvetica-Bold",
                       fontcolor="#333333")

        def nid(level: int, path: int) -> str:
            return f"n_{level}_{path}"

        dot.node(nid(0, 0), "", shape="point", width="0.12", height="0.12")
        dot.edge("IE", nid(0, 0), style="bold", penwidth="2")

        for j in range(n):
            _, p_succ = branch_probs[j]
            p_fail = 1.0 - p_succ
            num_nodes_at_level = 2 ** j

            for path in range(num_nodes_at_level):
                parent = nid(j, path)

                s_child = nid(j + 1, path * 2)
                dot.node(s_child, "", shape="point",
                         width="0.12", height="0.12")
                dot.edge(parent, s_child,
                         label=f" S ({p_succ:.4f})",
                         color="#2E7D32", fontcolor="#2E7D32",
                         penwidth="1.3")

                f_child = nid(j + 1, path * 2 + 1)
                dot.node(f_child, "", shape="point",
                         width="0.12", height="0.12")
                dot.edge(parent, f_child,
                         label=f" F ({p_fail:.4f})",
                         color="#C62828", fontcolor="#C62828",
                         penwidth="1.3")

        outcome_labels = self.et.outcome_labels
        num_outcomes = 2 ** n
        for idx in range(num_outcomes):
            leaf_node = nid(n, idx)

            custom_label = ""
            if idx < len(outcome_labels) and outcome_labels[idx]:
                custom_label = outcome_labels[idx]

            if idx < len(self.outcomes):
                oc = self.outcomes[idx]
                seq_str = ", ".join(
                    f"{name}: {status[0]}" for name, status in oc["sequence"]
                )
                parts = [f"#{idx + 1}"]
                if custom_label:
                    parts.append(custom_label)
                parts.append(seq_str)
                parts.append(f"P = {oc['probability']:.4e}")
                parts.append(f"Freq = {oc['frequency']:.4e}")
                label = "\n".join(parts)
            else:
                label = f"Outcome #{idx + 1}"
                if custom_label:
                    label += f"\n{custom_label}"

            if idx < len(self.outcomes):
                failures = sum(1 for _, s in self.outcomes[idx]["sequence"]
                               if s == "Failure")
                if failures == 0:
                    fill = "#C8E6C9"
                elif failures == n:
                    fill = "#FFCDD2"
                else:
                    fill = "#FFF9C4"
            else:
                fill = "#E0E0E0"

            dot.node(f"out_{idx}", label, shape="box",
                     style="filled,rounded", fillcolor=fill,
                     fontsize="8", width="2.2")
            dot.edge(leaf_node, f"out_{idx}", style="dashed",
                     color="#999999")

        if output_path is None:
            output_path = os.path.join(tempfile.gettempdir(),
                                       "event_tree_diagram")

        _render_dot(dot, output_path)
        return f"{output_path}.{fmt}"


class SeriesParallelVisualizer:
    """
    Generates a block diagram for a recursive series-parallel system.

    Visual distinction:
      - Series groups: solid blue border, "── SERİ ──" label
      - Parallel groups: bold dashed orange border, "═ PARALEL ═" label,
        visible split/merge diamond nodes
      - Components: colored boxes with reliability bar
    """

    def __init__(self, root: SPNode):
        self.root = root
        self._edges: list[tuple[str, str, dict]] = []
        self._counter = 0

    def _uid(self) -> str:
        self._counter += 1
        return f"_n{self._counter}"

    def _add_node(self, graph, node: SPNode) -> tuple[str, str]:
        if node.node_type == "component":
            nid = f"c_{node.id}"
            r = node.reliability
            f_val = 1.0 - r
            if r >= 0.99:
                fill = "#C8E6C9"
            elif r >= 0.95:
                fill = "#FFF9C4"
            else:
                fill = "#FFCDD2"
            label = (f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2">'
                     f'<TR><TD><B>{node.name}</B></TD></TR>'
                     f'<TR><TD><FONT POINT-SIZE="9" COLOR="#1565C0">'
                     f'R = {r:.6f}</FONT></TD></TR>'
                     f'<TR><TD><FONT POINT-SIZE="9" COLOR="#C62828">'
                     f'F = {f_val:.4e}</FONT></TD></TR>'
                     f'</TABLE>>')
            graph.node(nid, label, shape="box", style="filled,rounded",
                       fillcolor=fill, width="1.6", height="0.8",
                       penwidth="1.5", color="#666666")
            return nid, nid

        r_group = node.calc_reliability()
        f_group = 1.0 - r_group
        in_id = f"in_{node.id}"
        out_id = f"out_{node.id}"

        is_series = node.node_type == "series"

        if is_series:
            color = "#1565C0"
            border_style = "rounded,bold"
            type_label = "-- SERI --"
            pw = "2.5"
        else:
            color = "#E65100"
            border_style = "rounded,dashed,bold"
            type_label = "= PARALEL ="
            pw = "3"

        group_label = (f'{type_label}  {node.name}\n'
                       f'R = {r_group:.4e}  |  F = {f_group:.4e}')

        with graph.subgraph(name=f"cluster_{node.id}") as sub:
            sub.attr(
                label=group_label,
                style=border_style, color=color, penwidth=pw,
                fontsize="11", fontname="Helvetica-Bold", fontcolor=color,
                bgcolor="#FFFFFF" if is_series else "#FFF8F0",
                margin="16",
            )

            if is_series:
                sub.node(in_id, "", shape="point",
                         width="0.08", height="0.08", color=color)
                sub.node(out_id, "", shape="point",
                         width="0.08", height="0.08", color=color)
            else:
                sub.node(in_id, "◀", shape="diamond",
                         width="0.35", height="0.35",
                         style="filled", fillcolor="#FFE0B2",
                         color=color, penwidth="2",
                         fontsize="8", fontcolor=color)
                sub.node(out_id, "▶", shape="diamond",
                         width="0.35", height="0.35",
                         style="filled", fillcolor="#FFE0B2",
                         color=color, penwidth="2",
                         fontsize="8", fontcolor=color)

            if not node.children:
                self._edges.append((in_id, out_id, {}))
            elif is_series:
                prev = in_id
                for child in node.children:
                    c_in, c_out = self._add_node(sub, child)
                    self._edges.append((prev, c_in,
                                        {"color": color, "penwidth": "2"}))
                    prev = c_out
                self._edges.append((prev, out_id,
                                    {"color": color, "penwidth": "2"}))
            else:
                for child in node.children:
                    c_in, c_out = self._add_node(sub, child)
                    self._edges.append((in_id, c_in,
                                        {"color": color, "penwidth": "1.5",
                                         "style": "bold"}))
                    self._edges.append((c_out, out_id,
                                        {"color": color, "penwidth": "1.5",
                                         "style": "bold"}))

        return in_id, out_id

    def render(self, output_path: str | None = None, fmt: str = "png") -> str:
        r_sys = self.root.calc_reliability()
        f_sys = 1.0 - r_sys

        dot = graphviz.Digraph(
            "SeriesParallel",
            format=fmt,
            graph_attr={
                "rankdir": "LR",
                "splines": "spline",
                "nodesep": "0.6",
                "ranksep": "1.2",
                "bgcolor": "#FAFAFA",
                "label": (f"Sistem Guvenilirligi:  R = {r_sys:.6e}   |   "
                          f"F = {f_sys:.6e}"),
                "labelloc": "t",
                "fontsize": "16",
                "fontname": "Helvetica-Bold",
                "pad": "0.5",
            },
            node_attr={"fontname": "Helvetica", "fontsize": "10"},
            edge_attr={"color": "#555555", "penwidth": "1.8",
                       "arrowhead": "vee"},
        )

        dot.node("IN", "Giris", shape="circle", style="filled",
                 fillcolor="#1976D2", fontcolor="white", width="0.9",
                 fontname="Helvetica-Bold", penwidth="2")
        dot.node("OUT", "Cikis", shape="circle", style="filled",
                 fillcolor="#2E7D32", fontcolor="white", width="0.9",
                 fontname="Helvetica-Bold", penwidth="2")

        self._edges = []
        root_in, root_out = self._add_node(dot, self.root)
        self._edges.append(("IN", root_in, {"penwidth": "2.5", "color": "#333333"}))
        self._edges.append((root_out, "OUT", {"penwidth": "2.5", "color": "#333333"}))

        for src, dst, attrs in self._edges:
            dot.edge(src, dst, **attrs)

        if output_path is None:
            output_path = os.path.join(tempfile.gettempdir(), "sp_diagram")

        _render_dot(dot, output_path)
        return f"{output_path}.{fmt}"
