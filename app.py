"""
HÖA Analizörü — Birleşik tek sayfa arayüz.

PyQt6 ile geliştirilmiştir. Üç analiz modu tek pencerede:
  - Seri / Paralel — Sistem güvenilirlik hesaplayıcı
  - Hata Ağacı     — Kapılar + temel olaylar + tepe olay hesaplaması
  - Olay Ağacı     — Başlatıcı olay + dallar + sonuç dizileri

Sol panel: veri girişi (mod bazlı)
Sağ panel: diyagram + sonuçlar (her değişiklikte otomatik güncelleme)
"""

import os
import sys
import math
import traceback

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QFont, QAction
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QScrollArea, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QFileDialog, QMessageBox, QSplitter, QGroupBox,
    QDoubleSpinBox, QStackedWidget, QSizePolicy,
    QTreeWidget, QTreeWidgetItem,
)

from models import (
    BasicEvent, Gate, GateType, FaultTree,
    EventTreeBranch, EventTree, Project, SPNode, SPConfig,
)
from engine import (
    FaultTreeEngine, EventTreeEngine, MinimalCutSetEngine, ImportanceMeasures,
)
from visualization import (
    FaultTreeVisualizer, EventTreeVisualizer, SeriesParallelVisualizer,
)


STYLE = """
QMainWindow { background-color: #f5f5f5; }
QGroupBox {
    font-weight: bold; border: 1px solid #cccccc;
    border-radius: 4px; margin-top: 12px; padding-top: 16px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton {
    background-color: #1976D2; color: white; border: none;
    padding: 6px 16px; border-radius: 4px; font-weight: bold;
}
QPushButton:hover { background-color: #1565C0; }
QPushButton:pressed { background-color: #0D47A1; }
QPushButton#deleteBtn { background-color: #D32F2F; }
QPushButton#deleteBtn:hover { background-color: #B71C1C; }
QPushButton#modeBtn {
    background-color: #e0e0e0; color: #333; border: 2px solid #bbb;
    padding: 10px 28px; font-size: 13px; border-radius: 6px;
}
QPushButton#modeBtn:checked {
    background-color: #1976D2; color: white; border-color: #1565C0;
}
QPushButton#vizBtn { background-color: #E65100; }
QPushButton#vizBtn:hover { background-color: #BF360C; }
QTableWidget {
    background-color: #ffffff; color: #222222;
    gridline-color: #e0e0e0; selection-background-color: #BBDEFB;
    selection-color: #222222; alternate-background-color: #f9f9f9;
}
QTableWidget QTableCornerButton::section {
    background-color: #e0e0e0; border: 1px solid #cccccc;
}
QHeaderView::section {
    background-color: #e0e0e0; padding: 4px; border: 1px solid #cccccc;
    font-weight: bold;
}
"""

# ──────────────────────────────────────────────────────────────────────
#  Diyagram görüntüleyici diyaloğu
# ──────────────────────────────────────────────────────────────────────

class ImageViewerDialog(QDialog):
    def __init__(self, image_path: str, title: str = "Diyagram", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 750)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        label = QLabel()
        pixmap = QPixmap(image_path)
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        btn = QPushButton("Kapat")
        btn.clicked.connect(self.close)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


# ──────────────────────────────────────────────────────────────────────
#  Temel Olay Diyaloğu
# ──────────────────────────────────────────────────────────────────────

class EventDialog(QDialog):
    def __init__(self, event: BasicEvent | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Olay Ekle" if event is None else "Olay Düzenle")
        self.setMinimumWidth(400)
        self.event = event or BasicEvent()
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow("Olay Adı:", self.name_edit)

        self.mode_group = QButtonGroup(self)
        self.radio_direct = QRadioButton("Doğrudan Güvenilirlik (R)")
        self.radio_lambda = QRadioButton("Zamana Bağlı (λ, t)")
        self.mode_group.addButton(self.radio_direct, 0)
        self.mode_group.addButton(self.radio_lambda, 1)
        mode_box = QGroupBox("Giriş Modu")
        ml = QVBoxLayout(mode_box)
        ml.addWidget(self.radio_direct)
        ml.addWidget(self.radio_lambda)
        layout.addRow(mode_box)

        self.r_spin = QDoubleSpinBox()
        self.r_spin.setRange(0.0, 1.0)
        self.r_spin.setDecimals(8)
        self.r_spin.setSingleStep(0.01)
        self.r_spin.setValue(0.99)
        layout.addRow("Güvenilirlik (R):", self.r_spin)

        self.f_preview = QLabel("")
        self.f_preview.setStyleSheet("color: #C62828; font-weight: bold;")
        layout.addRow("Arıza Olasılığı:", self.f_preview)

        self.lambda_spin = QDoubleSpinBox()
        self.lambda_spin.setRange(0.0, 1e12)
        self.lambda_spin.setDecimals(8)
        self.lambda_spin.setSingleStep(0.0001)
        layout.addRow("Arıza Oranı (λ) [1/saat]:", self.lambda_spin)

        self.t_spin = QDoubleSpinBox()
        self.t_spin.setRange(0.0, 1e12)
        self.t_spin.setDecimals(4)
        self.t_spin.setSingleStep(1.0)
        layout.addRow("Zaman (t) [saat]:", self.t_spin)

        self.calc_preview = QLabel("R = e^(-λt) = —")
        self.calc_preview.setStyleSheet("color: #1976D2; font-weight: bold;")
        layout.addRow("Hesaplanan:", self.calc_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.mode_group.idToggled.connect(self._on_mode_changed)
        self.r_spin.valueChanged.connect(self._update_preview)
        self.lambda_spin.valueChanged.connect(self._update_preview)
        self.t_spin.valueChanged.connect(self._update_preview)

    def _load_data(self):
        self.name_edit.setText(self.event.name)
        if self.event.use_time_dependent:
            self.radio_lambda.setChecked(True)
            self.lambda_spin.setValue(self.event.failure_rate or 0.0)
            self.t_spin.setValue(self.event.time or 0.0)
        else:
            self.radio_direct.setChecked(True)
            self.r_spin.setValue(
                self.event.reliability if self.event.reliability is not None else 0.99)
        self._on_mode_changed()
        self._update_preview()

    def _on_mode_changed(self):
        is_lambda = self.radio_lambda.isChecked()
        self.r_spin.setEnabled(not is_lambda)
        self.f_preview.setVisible(not is_lambda)
        self.lambda_spin.setEnabled(is_lambda)
        self.t_spin.setEnabled(is_lambda)
        self.calc_preview.setVisible(is_lambda)
        self._update_preview()

    def _update_preview(self):
        if self.radio_lambda.isChecked():
            lam = self.lambda_spin.value()
            t = self.t_spin.value()
            r = math.exp(-lam * t)
            f = 1.0 - r
            self.calc_preview.setText(
                f"R = e^(-{lam:.6g}×{t:.4g}) = {r:.8f}   F = {f:.6e}")
        else:
            r = self.r_spin.value()
            f = 1.0 - r
            self.f_preview.setText(f"F = 1 - R = {f:.6e}")

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Uyarı", "Olay adı boş olamaz.")
            return
        self.event.name = name
        self.event.use_time_dependent = self.radio_lambda.isChecked()
        if self.event.use_time_dependent:
            self.event.failure_rate = self.lambda_spin.value()
            self.event.time = self.t_spin.value()
            self.event.reliability = None
        else:
            self.event.reliability = self.r_spin.value()
            self.event.failure_rate = None
            self.event.time = None
        self.accept()

    def get_event(self) -> BasicEvent:
        return self.event


# ──────────────────────────────────────────────────────────────────────
#  Kapı Diyaloğu
# ──────────────────────────────────────────────────────────────────────

class GateDialog(QDialog):
    def __init__(self, gate: Gate | None, basic_events: dict[str, BasicEvent],
                 gates: dict[str, Gate], exclude_id: str | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kapı Ekle" if gate is None else "Kapı Düzenle")
        self.setMinimumWidth(420)
        self.setMinimumHeight(400)
        self.gate = gate or Gate()
        self.basic_events = basic_events
        self.all_gates = gates
        self.exclude_id = exclude_id
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow("Kapı Adı:", self.name_edit)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["AND", "OR", "VOTE"])
        layout.addRow("Kapı Tipi:", self.type_combo)

        from PyQt6.QtWidgets import QSpinBox
        self.k_spin = QSpinBox()
        self.k_spin.setRange(1, 99)
        self.k_spin.setValue(2)
        self.k_label = QLabel("k (min. arıza sayısı):")
        layout.addRow(self.k_label, self.k_spin)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        layout.addRow(QLabel("Alt Elemanları Seçin:"))
        self.children_list = QListWidget()
        self.children_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        layout.addRow(self.children_list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_type_changed(self, text: str):
        is_vote = text == "VOTE"
        self.k_spin.setVisible(is_vote)
        self.k_label.setVisible(is_vote)

    def _load_data(self):
        self.name_edit.setText(self.gate.name)
        self.type_combo.setCurrentText(self.gate.gate_type.value)
        self.k_spin.setValue(self.gate.vote_k)
        self._on_type_changed(self.gate.gate_type.value)
        for eid, ev in self.basic_events.items():
            item = QListWidgetItem(f"[Olay] {ev.name} ({eid})")
            item.setData(Qt.ItemDataRole.UserRole, eid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if eid in self.gate.children
                else Qt.CheckState.Unchecked)
            self.children_list.addItem(item)
        for gid, g in self.all_gates.items():
            if gid == self.exclude_id:
                continue
            item = QListWidgetItem(
                f"[Kapı-{g.gate_type.value}] {g.name} ({gid})")
            item.setData(Qt.ItemDataRole.UserRole, gid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if gid in self.gate.children
                else Qt.CheckState.Unchecked)
            self.children_list.addItem(item)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Uyarı", "Kapı adı boş olamaz.")
            return
        self.gate.name = name
        self.gate.gate_type = GateType(self.type_combo.currentText())
        self.gate.children = []
        for i in range(self.children_list.count()):
            item = self.children_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.gate.children.append(item.data(Qt.ItemDataRole.UserRole))
        if not self.gate.children:
            QMessageBox.warning(self, "Uyarı",
                                "Kapının en az bir alt elemanı olmalıdır.")
            return
        if self.gate.gate_type == GateType.VOTE:
            self.gate.vote_k = self.k_spin.value()
            if self.gate.vote_k > len(self.gate.children):
                QMessageBox.warning(
                    self, "Uyarı",
                    f"k ({self.gate.vote_k}) alt eleman sayısından "
                    f"({len(self.gate.children)}) büyük olamaz.")
                return
        self.accept()

    def get_gate(self) -> Gate:
        return self.gate


# ──────────────────────────────────────────────────────────────────────
#  Dal Diyaloğu
# ──────────────────────────────────────────────────────────────────────

class BranchDialog(QDialog):
    def __init__(self, branch: EventTreeBranch | None,
                 basic_events: dict[str, BasicEvent], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dal Ekle" if branch is None else "Dal Düzenle")
        self.setMinimumWidth(380)
        self.branch = branch or EventTreeBranch()
        self.basic_events = basic_events
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow("Dal Adı:", self.name_edit)

        self.mode_group = QButtonGroup(self)
        self.radio_direct = QRadioButton("Doğrudan P(başarı)")
        self.radio_event = QRadioButton("Temel Olaydan (R)")
        self.mode_group.addButton(self.radio_direct, 0)
        self.mode_group.addButton(self.radio_event, 1)
        mode_box = QGroupBox("Olasılık Kaynağı")
        ml = QVBoxLayout(mode_box)
        ml.addWidget(self.radio_direct)
        ml.addWidget(self.radio_event)
        layout.addRow(mode_box)

        self.prob_spin = QDoubleSpinBox()
        self.prob_spin.setRange(0.0, 1.0)
        self.prob_spin.setDecimals(8)
        self.prob_spin.setSingleStep(0.01)
        self.prob_spin.setValue(0.95)
        layout.addRow("P(başarı):", self.prob_spin)

        self.event_combo = QComboBox()
        self.event_combo.addItem("— Seçin —", None)
        for eid, ev in self.basic_events.items():
            self.event_combo.addItem(
                f"{ev.name} (R={ev.get_reliability():.6f})", eid)
        layout.addRow("Temel Olay:", self.event_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.mode_group.idToggled.connect(self._on_mode_changed)

    def _load_data(self):
        self.name_edit.setText(self.branch.name)
        if self.branch.basic_event_id:
            self.radio_event.setChecked(True)
            idx = self.event_combo.findData(self.branch.basic_event_id)
            if idx >= 0:
                self.event_combo.setCurrentIndex(idx)
        else:
            self.radio_direct.setChecked(True)
            if self.branch.success_probability is not None:
                self.prob_spin.setValue(self.branch.success_probability)
        self._on_mode_changed()

    def _on_mode_changed(self):
        is_event = self.radio_event.isChecked()
        self.prob_spin.setEnabled(not is_event)
        self.event_combo.setEnabled(is_event)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Uyarı", "Dal adı boş olamaz.")
            return
        self.branch.name = name
        if self.radio_event.isChecked():
            eid = self.event_combo.currentData()
            if eid is None:
                QMessageBox.warning(self, "Uyarı",
                                    "Lütfen bir temel olay seçin.")
                return
            self.branch.basic_event_id = eid
            self.branch.success_probability = None
        else:
            self.branch.basic_event_id = None
            self.branch.success_probability = self.prob_spin.value()
        self.accept()

    def get_branch(self) -> EventTreeBranch:
        return self.branch


# ──────────────────────────────────────────────────────────────────────
#  Seri/Paralel Düğüm Diyaloğu
# ──────────────────────────────────────────────────────────────────────

class SPNodeDialog(QDialog):
    def __init__(self, node: SPNode | None = None, allow_component: bool = True,
                 parent=None):
        super().__init__(parent)
        is_new = node is None
        self.setWindowTitle("Düğüm Ekle" if is_new else "Düğüm Düzenle")
        self.setMinimumWidth(360)
        self.node = node or SPNode()
        self.allow_component = allow_component
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow("Ad:", self.name_edit)

        self.type_combo = QComboBox()
        if self.allow_component:
            self.type_combo.addItem("Bileşen", "component")
        self.type_combo.addItem("Seri Grup", "series")
        self.type_combo.addItem("Paralel Grup", "parallel")
        layout.addRow("Tip:", self.type_combo)

        self.r_spin = QDoubleSpinBox()
        self.r_spin.setRange(0.0, 1.0)
        self.r_spin.setDecimals(8)
        self.r_spin.setSingleStep(0.01)
        self.r_spin.setValue(0.95)
        self.r_label = QLabel("Güvenilirlik (R):")
        layout.addRow(self.r_label, self.r_spin)

        self.f_preview = QLabel("")
        self.f_preview.setStyleSheet("color: #C62828; font-weight: bold;")
        layout.addRow("Arıza Olasılığı:", self.f_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.r_spin.valueChanged.connect(self._update_preview)

    def _load_data(self):
        self.name_edit.setText(self.node.name)
        idx = self.type_combo.findData(self.node.node_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.r_spin.setValue(self.node.reliability)
        self._on_type_changed()
        self._update_preview()

    def _on_type_changed(self):
        is_comp = self.type_combo.currentData() == "component"
        self.r_spin.setVisible(is_comp)
        self.r_label.setVisible(is_comp)
        self.f_preview.setVisible(is_comp)

    def _update_preview(self):
        r = self.r_spin.value()
        self.f_preview.setText(f"F = 1 - R = {1.0 - r:.6e}")

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Uyarı", "Ad boş olamaz.")
            return
        self.node.name = name
        self.node.node_type = self.type_combo.currentData()
        if self.node.node_type == "component":
            self.node.reliability = self.r_spin.value()
            self.node.children = []
        self.accept()

    def get_node(self) -> SPNode:
        return self.node


# ──────────────────────────────────────────────────────────────────────
#  Ana Pencere — Birleşik Arayüz
# ──────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    MODE_SP = 0
    MODE_FT = 1
    MODE_ET = 2

    def __init__(self):
        super().__init__()
        self.project = Project()
        self._current_file: str | None = None
        self._current_mode = self.MODE_SP
        self._last_diagram_path: str | None = None
        self._ft_results: dict | None = None
        self._et_outcomes: list[dict] | None = None

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._auto_calculate)

        self._setup_window()
        self._setup_menu()
        self._setup_ui()
        self._set_mode(self.MODE_SP)

    # ── Pencere yapılandırması ──────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("HÖA Analizörü — Hata Ağacı & Olay Ağacı Analizi")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 850)
        self.setStyleSheet(STYLE)
        self.statusBar().showMessage("Hazır")

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("Dosya")

        a = QAction("Yeni Proje", self)
        a.setShortcut("Ctrl+N")
        a.triggered.connect(self._new_project)
        fm.addAction(a)

        a = QAction("Proje Aç...", self)
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self._open_project)
        fm.addAction(a)

        fm.addSeparator()

        a = QAction("Kaydet", self)
        a.setShortcut("Ctrl+S")
        a.triggered.connect(self._save_project)
        fm.addAction(a)

        a = QAction("Farklı Kaydet...", self)
        a.setShortcut("Ctrl+Shift+S")
        a.triggered.connect(self._save_as_project)
        fm.addAction(a)

        fm.addSeparator()

        a = QAction("PDF Rapor Oluştur...", self)
        a.setShortcut("Ctrl+P")
        a.triggered.connect(self._export_pdf)
        fm.addAction(a)

        fm.addSeparator()

        a = QAction("Çıkış", self)
        a.setShortcut("Ctrl+Q")
        a.triggered.connect(self.close)
        fm.addAction(a)

        em = mb.addMenu("Örnekler")

        ft_menu = em.addMenu("Hata Ağacı (FTA)")
        for label, slot in [
            ("Redundant Pompa Sistemi", self._example_redundant_pump),
            ("Yangın Güvenlik Sistemi", self._example_fire_safety),
            ("Acil Dizel Jeneratör (VOTE k/n)", self._example_diesel_vote),
            ("Nükleer Soğutma Kaybı", self._example_nuclear_cooling),
        ]:
            a = QAction(label, self)
            a.triggered.connect(slot)
            ft_menu.addAction(a)

        et_menu = em.addMenu("Olay Ağacı (ETA)")
        for label, slot in [
            ("Büyük LOCA Senaryosu", self._example_loca_et),
            ("Kimyasal Tesis Sızıntısı", self._example_chemical_et),
        ]:
            a = QAction(label, self)
            a.triggered.connect(slot)
            et_menu.addAction(a)

        sp_menu = em.addMenu("Seri / Paralel")
        for label, slot in [
            ("Güç Kaynağı Sistemi", self._example_power_supply_sp),
            ("Su Pompalama İstasyonu", self._example_pump_station_sp),
        ]:
            a = QAction(label, self)
            a.triggered.connect(slot)
            sp_menu.addAction(a)

        hm = mb.addMenu("Yardım")
        a = QAction("Nasıl Kullanılır?", self)
        a.triggered.connect(self._show_guide)
        hm.addAction(a)
        hm.addSeparator()
        a = QAction("Hakkında", self)
        a.triggered.connect(self._show_about)
        hm.addAction(a)

    # ── Ana arayüz ─────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(8)

        # -- Mod seçici çubuğu --
        mode_bar = QHBoxLayout()
        mode_bar.setSpacing(6)
        self._mode_buttons: list[QPushButton] = []
        for label in ["Seri / Paralel", "Hata Ağacı", "Olay Ağacı"]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("modeBtn")
            btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)
            self._mode_buttons.append(btn)
            mode_bar.addWidget(btn)
        mode_bar.addStretch()
        self._mode_buttons[0].clicked.connect(lambda: self._set_mode(0))
        self._mode_buttons[1].clicked.connect(lambda: self._set_mode(1))
        self._mode_buttons[2].clicked.connect(lambda: self._set_mode(2))
        root.addLayout(mode_bar)

        # -- Ana splitter --
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # SOL PANEL
        left = QWidget()
        left.setMinimumWidth(380)
        self._left_vbox = QVBoxLayout(left)
        self._left_vbox.setContentsMargins(0, 0, 0, 0)
        self._left_vbox.setSpacing(4)

        # Temel Olaylar grubu (FT ve ET modlarında görünür)
        self._events_group = self._build_events_group()
        self._left_vbox.addWidget(self._events_group)

        # Mod bazlı yığın
        self._mode_stack = QStackedWidget()
        self._sp_panel = self._build_sp_panel()
        self._ft_panel = self._build_ft_panel()
        self._et_panel = self._build_et_panel()
        self._mode_stack.addWidget(self._sp_panel)
        self._mode_stack.addWidget(self._ft_panel)
        self._mode_stack.addWidget(self._et_panel)
        self._left_vbox.addWidget(self._mode_stack, 1)

        scroll_left = QScrollArea()
        scroll_left.setWidgetResizable(True)
        scroll_left.setWidget(left)
        scroll_left.setFrameShape(QScrollArea.Shape.NoFrame)
        self._main_splitter.addWidget(scroll_left)

        # SAĞ PANEL
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Diyagram alanı
        diagram_widget = QWidget()
        dg_layout = QVBoxLayout(diagram_widget)
        dg_layout.setContentsMargins(0, 0, 0, 0)

        self._diagram_scroll = QScrollArea()
        self._diagram_scroll.setWidgetResizable(True)
        self._diagram_label = QLabel("Diyagram burada görünecek.")
        self._diagram_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._diagram_label.setStyleSheet("color: #999; padding: 30px;")
        self._diagram_scroll.setWidget(self._diagram_label)
        dg_layout.addWidget(self._diagram_scroll)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        self._save_diagram_btn = QPushButton("Diyagramı Kaydet")
        self._save_diagram_btn.clicked.connect(self._save_diagram)
        btn_bar.addWidget(self._save_diagram_btn)
        self._fullscreen_btn = QPushButton("Büyüt")
        self._fullscreen_btn.setObjectName("vizBtn")
        self._fullscreen_btn.clicked.connect(self._show_fullscreen_diagram)
        btn_bar.addWidget(self._fullscreen_btn)
        dg_layout.addLayout(btn_bar)

        right_splitter.addWidget(diagram_widget)

        # Sonuç alanı (mod bazlı yığın)
        self._results_stack = QStackedWidget()

        self._sp_results = QTextEdit()
        self._sp_results.setReadOnly(True)
        self._sp_results.setFont(QFont("Monospace", 10))
        self._results_stack.addWidget(self._sp_results)

        self._ft_results_text = QTextEdit()
        self._ft_results_text.setReadOnly(True)
        self._ft_results_text.setFont(QFont("Monospace", 10))
        self._results_stack.addWidget(self._ft_results_text)

        et_result_w = QWidget()
        et_lay = QVBoxLayout(et_result_w)
        et_lay.setContentsMargins(0, 0, 0, 0)
        self._outcome_table = QTableWidget(0, 5)
        self._outcome_table.setHorizontalHeaderLabels(
            ["#", "Dizi", "Olasılık", "Frekans", "Etiket"])
        self._outcome_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._outcome_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch)
        self._outcome_table.setAlternatingRowColors(True)
        self._outcome_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked)
        self._outcome_table.cellChanged.connect(self._on_outcome_label_changed)
        et_lay.addWidget(self._outcome_table)
        self._results_stack.addWidget(et_result_w)

        right_splitter.addWidget(self._results_stack)
        right_splitter.setSizes([420, 300])

        right_layout.addWidget(right_splitter)
        self._main_splitter.addWidget(right)
        self._main_splitter.setSizes([420, 600])

        root.addWidget(self._main_splitter, 1)
        self.setCentralWidget(central)

    # ── Temel Olaylar grubu (paylaşımlı) ───────────────────────────

    def _build_events_group(self) -> QGroupBox:
        grp = QGroupBox("Temel Olaylar")
        lay = QVBoxLayout(grp)

        self._events_table = QTableWidget(0, 5)
        self._events_table.setHorizontalHeaderLabels(
            ["Kimlik", "Ad", "Mod", "R", "F"])
        self._events_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._events_table.setAlternatingRowColors(True)
        self._events_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._events_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._events_table.setMaximumHeight(180)
        lay.addWidget(self._events_table)

        bl = QHBoxLayout()
        b = QPushButton("Olay Ekle")
        b.clicked.connect(self._add_event)
        bl.addWidget(b)
        b = QPushButton("Düzenle")
        b.clicked.connect(self._edit_event)
        bl.addWidget(b)
        b = QPushButton("Sil")
        b.setObjectName("deleteBtn")
        b.clicked.connect(self._delete_event)
        bl.addWidget(b)
        bl.addStretch()
        lay.addLayout(bl)
        return grp

    # ── Seri / Paralel paneli ──────────────────────────────────────

    def _build_sp_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        grp = QGroupBox("Sistem Yapısı (Ağaç)")
        gl = QVBoxLayout(grp)

        self._sp_tree = QTreeWidget()
        self._sp_tree.setHeaderLabels(["Ad", "Tip", "R", "F"])
        self._sp_tree.setColumnCount(4)
        self._sp_tree.setAlternatingRowColors(True)
        self._sp_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        gl.addWidget(self._sp_tree)

        bl = QHBoxLayout()
        b = QPushButton("Bileşen Ekle")
        b.clicked.connect(self._sp_add_node)
        bl.addWidget(b)
        b = QPushButton("Grup Ekle")
        b.clicked.connect(self._sp_add_group)
        bl.addWidget(b)
        b = QPushButton("Düzenle")
        b.clicked.connect(self._sp_edit_node)
        bl.addWidget(b)
        b = QPushButton("Sil")
        b.setObjectName("deleteBtn")
        b.clicked.connect(self._sp_delete_node)
        bl.addWidget(b)
        bl.addStretch()
        gl.addLayout(bl)
        lay.addWidget(grp)

        lay.addStretch()
        return w

    # ── Hata Ağacı paneli ──────────────────────────────────────────

    def _build_ft_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        # Kapılar
        gate_grp = QGroupBox("Mantık Kapıları")
        gl = QVBoxLayout(gate_grp)

        self._gate_table = QTableWidget(0, 4)
        self._gate_table.setHorizontalHeaderLabels(
            ["Kimlik", "Ad", "Tip", "Alt Elemanlar"])
        self._gate_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self._gate_table.setAlternatingRowColors(True)
        self._gate_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._gate_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        gl.addWidget(self._gate_table)

        bl = QHBoxLayout()
        b = QPushButton("Kapı Ekle")
        b.clicked.connect(self._add_gate)
        bl.addWidget(b)
        b = QPushButton("Düzenle")
        b.clicked.connect(self._edit_gate)
        bl.addWidget(b)
        b = QPushButton("Sil")
        b.setObjectName("deleteBtn")
        b.clicked.connect(self._delete_gate)
        bl.addWidget(b)
        bl.addStretch()
        gl.addLayout(bl)
        lay.addWidget(gate_grp)

        # Tepe Olay
        top_grp = QGroupBox("Tepe Olay")
        tl = QHBoxLayout(top_grp)
        tl.addWidget(QLabel("Tepe Kapı:"))
        self._top_combo = QComboBox()
        self._top_combo.currentIndexChanged.connect(self._on_top_changed)
        tl.addWidget(self._top_combo, 1)
        lay.addWidget(top_grp)

        lay.addStretch()
        return w

    # ── Olay Ağacı paneli ──────────────────────────────────────────

    def _build_et_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        # Başlatıcı Olay
        ie_grp = QGroupBox("Başlatıcı Olay")
        il = QFormLayout(ie_grp)
        self._ie_name = QLineEdit()
        self._ie_freq = QDoubleSpinBox()
        self._ie_freq.setRange(0.0, 1e20)
        self._ie_freq.setDecimals(6)
        self._ie_freq.setSingleStep(0.001)
        self._ie_freq.setValue(1.0)
        il.addRow("Ad:", self._ie_name)
        il.addRow("Frekans:", self._ie_freq)
        self._ie_name.textChanged.connect(self._sync_ie)
        self._ie_freq.valueChanged.connect(self._sync_ie)
        lay.addWidget(ie_grp)

        # Dallar
        br_grp = QGroupBox("Dallar (Güvenlik Sistemleri)")
        bl_lay = QVBoxLayout(br_grp)

        self._branch_table = QTableWidget(0, 3)
        self._branch_table.setHorizontalHeaderLabels(
            ["Ad", "Kaynak", "P(başarı)"])
        self._branch_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._branch_table.setAlternatingRowColors(True)
        self._branch_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._branch_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        bl_lay.addWidget(self._branch_table)

        bl = QHBoxLayout()
        for text, slot in [
            ("Dal Ekle", self._add_branch),
            ("Düzenle", self._edit_branch),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            bl.addWidget(b)
        b = QPushButton("Sil")
        b.setObjectName("deleteBtn")
        b.clicked.connect(self._delete_branch)
        bl.addWidget(b)
        b = QPushButton("↑")
        b.setFixedWidth(32)
        b.clicked.connect(self._move_branch_up)
        bl.addWidget(b)
        b = QPushButton("↓")
        b.setFixedWidth(32)
        b.clicked.connect(self._move_branch_down)
        bl.addWidget(b)
        bl.addStretch()
        bl_lay.addLayout(bl)
        lay.addWidget(br_grp)

        lay.addStretch()
        return w

    # ── Mod değiştirme ─────────────────────────────────────────────

    def _set_mode(self, mode: int):
        self._current_mode = mode
        for i, btn in enumerate(self._mode_buttons):
            btn.setChecked(i == mode)
        self._events_group.setVisible(mode != self.MODE_SP)
        self._mode_stack.setCurrentIndex(mode)
        self._results_stack.setCurrentIndex(mode)

        if mode == self.MODE_FT:
            self._refresh_events_table()
            self._refresh_gate_table()
            self._refresh_top_combo()
        elif mode == self.MODE_ET:
            self._refresh_events_table()
            self._refresh_et_panel()
        elif mode == self.MODE_SP:
            self._refresh_sp_tree()

        self._auto_calculate()

    # ── Otomatik hesaplama (debounced) ─────────────────────────────

    def _schedule_auto_calc(self, *_args):
        self._debounce_timer.start()

    def _auto_calculate(self):
        self._debounce_timer.stop()
        if self._current_mode == self.MODE_SP:
            self._calc_sp()
        elif self._current_mode == self.MODE_FT:
            self._calc_ft()
        elif self._current_mode == self.MODE_ET:
            self._calc_et()

    # ── S/P hesaplama ──────────────────────────────────────────────

    def _calc_sp(self):
        root = self.project.sp_config.root
        if not root.children:
            self._sp_results.setPlainText(
                "Hesaplama için sisteme bileşen veya grup ekleyin.")
            self._clear_diagram()
            return

        r_sys = root.calc_reliability()

        lines = []
        lines.append("=" * 58)
        lines.append("   SERİ-PARALEL SİSTEM GÜVENİLİRLİK ANALİZİ")
        lines.append("=" * 58)
        lines.append("")
        lines.extend(self._sp_node_text(root, indent=1))
        lines.append("")
        lines.append("=" * 58)
        lines.append(f"  Sistem Güvenilirliği:     R = {r_sys:.8e}")
        lines.append(f"  Sistem Arıza Olasılığı:  F = {1.0 - r_sys:.8e}")
        lines.append("=" * 58)

        self._sp_results.setPlainText("\n".join(lines))

        try:
            viz = SeriesParallelVisualizer(root)
            path = viz.render()
            self._show_diagram(path)
        except Exception as e:
            self._clear_diagram()
            self.statusBar().showMessage(f"Diyagram hatası: {e}")

    def _sp_node_text(self, node: SPNode, indent: int = 0) -> list[str]:
        prefix = "  " * indent
        if node.node_type == "component":
            r = node.reliability
            return [f"{prefix}{node.name:24s} R = {r:.8f}  F = {1-r:.8f}"]

        type_str = "Seri" if node.node_type == "series" else "Paralel"
        lines = [f"{prefix}{node.name} ({type_str})"]
        for child in node.children:
            lines.extend(self._sp_node_text(child, indent + 1))

        child_rs = [c.calc_reliability() for c in node.children]
        r = node.calc_reliability()
        if node.node_type == "series":
            formula = " × ".join(f"{cr:.6f}" for cr in child_rs)
            lines.append(f"{prefix}  → R = {formula}")
            lines.append(f"{prefix}    = {r:.8e}")
        else:
            formula = " × ".join(f"(1-{cr:.6f})" for cr in child_rs)
            lines.append(f"{prefix}  → R = 1 - {formula}")
            lines.append(f"{prefix}    = {r:.8e}")
        return lines

    # ── FT hesaplama ───────────────────────────────────────────────

    def _calc_ft(self):
        ft = self.project.fault_tree
        if not ft.gates or ft.top_event_id is None:
            self._ft_results_text.setPlainText(
                "Hesaplama için kapı tanımlayın ve tepe olay seçin.")
            self._clear_diagram()
            return

        engine = FaultTreeEngine(ft)
        self._ft_results = engine.calculate()
        top = self._ft_results.get("_top_event", {})

        lines = []
        lines.append("=" * 50)
        lines.append("   HATA AĞACI ANALİZ SONUÇLARI")
        lines.append("=" * 50)
        lines.append("")

        if top["failure_probability"] is not None:
            lines.append(f"  TEPE OLAY: {ft.gates[top['id']].name}")
            lines.append(
                f"  Arıza Olasılığı (F) = {top['failure_probability']:.6e}")
            lines.append(
                f"  Güvenilirlik (R)    = {top['reliability']:.6e}")
        else:
            lines.append("  TEPE OLAY: Hesaplanamadı.")
        lines.append("")

        lines.append("-" * 50)
        lines.append("  TEMEL OLAYLAR")
        lines.append("-" * 50)
        for eid, ev in ft.basic_events.items():
            r = self._ft_results.get(eid, {})
            lines.append(
                f"  {ev.name:20s}  R = {r.get('reliability', 0):.6e}"
                f"  F = {r.get('failure_probability', 0):.6e}")
        lines.append("")

        lines.append("-" * 50)
        lines.append("  KAPILAR")
        lines.append("-" * 50)
        for gid, gate in ft.gates.items():
            r = self._ft_results.get(gid, {})
            marker = " ★" if gid == ft.top_event_id else ""
            type_str = gate.gate_type.value
            if gate.gate_type == GateType.VOTE:
                type_str = f"VOTE({gate.vote_k}/{len(gate.children)})"
            lines.append(
                f"  {gate.name:20s} [{type_str:>5s}]"
                f"  R = {r.get('reliability', 0):.6e}"
                f"  F = {r.get('failure_probability', 0):.6e}{marker}")

        lines.append("")
        lines.append("=" * 60)
        lines.append("   HESAPLAMA ADIMLARI")
        lines.append("=" * 60)
        for gid, gate in ft.gates.items():
            child_info = []
            for cid in gate.children:
                if cid in ft.basic_events:
                    ev = ft.basic_events[cid]
                    fp = ev.get_failure_probability()
                    child_info.append((ev.name, fp))
                elif cid in ft.gates:
                    g = ft.gates[cid]
                    fp = self._ft_results.get(cid, {}).get(
                        "failure_probability", 0)
                    child_info.append((g.name, fp))

            gate_fp = self._ft_results.get(gid, {}).get(
                "failure_probability", 0)
            marker = " ★ TEPE OLAY" if gid == ft.top_event_id else ""
            lines.append(f"\n  {gate.name}{marker}")

            if gate.gate_type == GateType.AND:
                lines.append("  Tip: AND — Tüm alt elemanlar arızalanmalı")
                lines.append("  F = F₁ × F₂ × ... × Fₙ")
                parts = []
                for name, fp in child_info:
                    parts.append(f"F({name})={fp:.4e}")
                lines.append(f"  F = {' × '.join(f'{fp:.4e}' for _, fp in child_info)}")
                lines.append(f"  F = {gate_fp:.6e}")

            elif gate.gate_type == GateType.OR:
                lines.append("  Tip: OR — Herhangi bir alt eleman arızalanırsa")
                lines.append("  F = 1 - (1-F₁)(1-F₂)...(1-Fₙ)")
                parts = " × ".join(
                    f"(1-{fp:.4e})" for _, fp in child_info)
                lines.append(f"  F = 1 - {parts}")
                lines.append(f"  F = {gate_fp:.6e}")

            elif gate.gate_type == GateType.VOTE:
                k = gate.vote_k
                n = len(child_info)
                lines.append(
                    f"  Tip: VOTE — {n} elemandan en az {k} tanesi "
                    f"arızalanmalı")
                lines.append(f"  F = P(≥{k}/{n} arıza)")
                for name, fp in child_info:
                    lines.append(f"    F({name}) = {fp:.4e}")
                lines.append(f"  F = {gate_fp:.6e}")

        mcs_engine = MinimalCutSetEngine(ft)
        mcs_list = mcs_engine.calculate()
        if mcs_list:
            mcs_probs = mcs_engine.mcs_probabilities(mcs_list)
            p_approx = mcs_engine.top_probability_from_mcs(mcs_list)

            lines.append("")
            lines.append("=" * 50)
            lines.append("   MİNİMAL KESİM KÜMELERİ (MCS)")
            lines.append("=" * 50)
            lines.append(f"  Toplam MCS sayısı: {len(mcs_list)}")
            lines.append(f"  P(tepe) ≈ Σ P(MCSᵢ) = {p_approx:.6e}")
            lines.append("")

            for i, (mcs, prob) in enumerate(mcs_probs, 1):
                names = []
                for eid in mcs:
                    ev = ft.basic_events.get(eid)
                    names.append(ev.name if ev else eid)
                order_str = f"{len(mcs)}. derece"
                lines.append(f"  MCS-{i:02d} ({order_str}): "
                             f"{' ∩ '.join(sorted(names))}")
                lines.append(f"          P = {prob:.6e}")

        imp_engine = ImportanceMeasures(ft)
        imp_results = imp_engine.calculate()
        if imp_results:
            lines.append("")
            lines.append("=" * 70)
            lines.append("   ÖNEM ÖLÇÜLERİ (IMPORTANCE MEASURES)")
            lines.append("=" * 70)
            lines.append(f"  {'Olay':<20s} {'Birnbaum':>10s} {'FV':>10s}"
                         f" {'RAW':>10s} {'RRW':>10s}")
            lines.append("  " + "-" * 64)
            sorted_imp = sorted(
                imp_results.items(),
                key=lambda x: x[1]["fussell_vesely"],
                reverse=True,
            )
            for eid, vals in sorted_imp:
                ev = ft.basic_events.get(eid)
                name = ev.name if ev else eid
                name_disp = name if len(name) <= 20 else name[:18] + ".."
                rrw_str = (f"{vals['rrw']:10.4f}"
                           if vals['rrw'] != float('inf') else "       ∞")
                lines.append(
                    f"  {name_disp:<20s} {vals['birnbaum']:10.4e}"
                    f" {vals['fussell_vesely']:10.4f}"
                    f" {vals['raw']:10.4f}{rrw_str}")
            lines.append("")
            lines.append("  Birnbaum : Bileşenin tepe olaya marjinal etkisi")
            lines.append("  FV       : Bileşenin toplam riske katkı oranı")
            lines.append("  RAW      : Bileşen arızalanırsa risk kaç kat artar")
            lines.append("  RRW      : Bileşen mükemmel olursa risk kaç kat azalır")

        self._ft_results_text.setPlainText("\n".join(lines))

        try:
            viz = FaultTreeVisualizer(ft, self._ft_results)
            path = viz.render()
            self._show_diagram(path)
        except Exception as e:
            self._clear_diagram()
            self.statusBar().showMessage(f"Diyagram hatası: {e}")

    # ── ET hesaplama ───────────────────────────────────────────────

    def _calc_et(self):
        et = self.project.event_tree
        events = self.project.fault_tree.basic_events

        if not et.branches:
            self._outcome_table.setRowCount(0)
            self._clear_diagram()
            return

        engine = EventTreeEngine(et, events)
        self._et_outcomes = engine.calculate()

        self._outcome_table.blockSignals(True)
        self._outcome_table.setRowCount(len(self._et_outcomes))
        for row, oc in enumerate(self._et_outcomes):
            seq_str = " → ".join(
                f"{name}:{status[0]}" for name, status in oc["sequence"])
            for col, text in enumerate([
                str(row + 1), seq_str,
                f"{oc['probability']:.6e}", f"{oc['frequency']:.6e}",
            ]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._outcome_table.setItem(row, col, item)

            label = ""
            if row < len(et.outcome_labels):
                label = et.outcome_labels[row]
            self._outcome_table.setItem(row, 4, QTableWidgetItem(label))
        self._outcome_table.blockSignals(False)

        try:
            viz = EventTreeVisualizer(et, self._et_outcomes, events)
            path = viz.render()
            self._show_diagram(path)
        except Exception as e:
            self._clear_diagram()
            self.statusBar().showMessage(f"Diyagram hatası: {e}")

    # ── Diyagram gösterme ──────────────────────────────────────────

    def _show_diagram(self, path: str):
        self._last_diagram_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            avail_w = self._diagram_scroll.width() - 30
            if pixmap.width() > avail_w and avail_w > 100:
                pixmap = pixmap.scaledToWidth(
                    avail_w, Qt.TransformationMode.SmoothTransformation)
            self._diagram_label.setPixmap(pixmap)
            self._diagram_label.setStyleSheet("")
        else:
            self._diagram_label.setText("Diyagram yüklenemedi.")
            self._diagram_label.setStyleSheet("color: #999; padding: 30px;")

    def _clear_diagram(self):
        self._last_diagram_path = None
        self._diagram_label.clear()
        self._diagram_label.setText("Diyagram burada görünecek.")
        self._diagram_label.setStyleSheet("color: #999; padding: 30px;")

    def _show_fullscreen_diagram(self):
        if self._last_diagram_path:
            title = ["Seri/Paralel", "Hata Ağacı", "Olay Ağacı"][
                self._current_mode] + " Diyagramı"
            dlg = ImageViewerDialog(self._last_diagram_path, title, self)
            dlg.exec()

    def _save_diagram(self):
        if not self._last_diagram_path or not os.path.exists(self._last_diagram_path):
            QMessageBox.information(self, "Bilgi",
                                    "Kaydedilecek diyagram yok.")
            return
        import shutil
        path, _ = QFileDialog.getSaveFileName(
            self, "Diyagramı Kaydet", "diyagram.png",
            "PNG Dosyaları (*.png);;Tüm Dosyalar (*)")
        if path:
            try:
                shutil.copy2(self._last_diagram_path, path)
                self.statusBar().showMessage(f"Diyagram kaydedildi: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Hata",
                                     f"Diyagram kaydedilemedi:\n{e}")

    # ── Temel olay işlemleri ───────────────────────────────────────

    def _refresh_events_table(self):
        events = self.project.fault_tree.basic_events
        self._events_table.setRowCount(len(events))
        for row, (eid, ev) in enumerate(events.items()):
            r = ev.get_reliability()
            f = ev.get_failure_probability()
            mode = "λt" if ev.use_time_dependent else "Doğrudan"
            for col, text in enumerate([eid, ev.name, mode,
                                        f"{r:.6e}", f"{f:.6e}"]):
                self._events_table.setItem(row, col, QTableWidgetItem(text))

    def _selected_event_id(self) -> str | None:
        row = self._events_table.currentRow()
        if row < 0:
            return None
        return self._events_table.item(row, 0).text()

    def _add_event(self):
        dlg = EventDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ev = dlg.get_event()
            self.project.fault_tree.basic_events[ev.id] = ev
            self._refresh_events_table()
            self._auto_calculate()

    def _edit_event(self):
        eid = self._selected_event_id()
        if eid is None:
            QMessageBox.information(self, "Bilgi",
                                    "Düzenlemek için bir olay seçin.")
            return
        ev = self.project.fault_tree.basic_events[eid]
        dlg = EventDialog(event=ev, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_events_table()
            self._auto_calculate()

    def _delete_event(self):
        eid = self._selected_event_id()
        if eid is None:
            QMessageBox.information(self, "Bilgi",
                                    "Silmek için bir olay seçin.")
            return
        ev = self.project.fault_tree.basic_events[eid]
        reply = QMessageBox.question(
            self, "Onay", f"'{ev.name}' olayı silinsin mi?")
        if reply == QMessageBox.StandardButton.Yes:
            del self.project.fault_tree.basic_events[eid]
            for gate in self.project.fault_tree.gates.values():
                if eid in gate.children:
                    gate.children.remove(eid)
            for br in self.project.event_tree.branches:
                if br.basic_event_id == eid:
                    br.basic_event_id = None
            self._refresh_events_table()
            if self._current_mode == self.MODE_FT:
                self._refresh_gate_table()
            self._auto_calculate()

    # ── S/P ağaç işlemleri ───────────────────────────────────────────

    def _refresh_sp_tree(self):
        self._sp_tree.clear()
        root = self.project.sp_config.root
        root_item = self._sp_make_tree_item(root)
        self._sp_tree.addTopLevelItem(root_item)
        self._sp_tree.expandAll()

    def _sp_make_tree_item(self, node: SPNode) -> QTreeWidgetItem:
        r = node.calc_reliability()
        types = {"component": "Bileşen", "series": "Seri", "parallel": "Paralel"}
        item = QTreeWidgetItem([
            node.name, types.get(node.node_type, "?"),
            f"{r:.6e}", f"{1.0 - r:.6e}",
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, node.id)
        for child in node.children:
            item.addChild(self._sp_make_tree_item(child))
        return item

    def _sp_selected_node(self) -> SPNode | None:
        items = self._sp_tree.selectedItems()
        if not items:
            return None
        nid = items[0].data(0, Qt.ItemDataRole.UserRole)
        return self._sp_find_node(nid)

    def _sp_find_node(self, node_id: str,
                      root: SPNode | None = None) -> SPNode | None:
        if root is None:
            root = self.project.sp_config.root
        if root.id == node_id:
            return root
        for child in root.children:
            found = self._sp_find_node(node_id, child)
            if found:
                return found
        return None

    def _sp_find_parent(self, node_id: str,
                        root: SPNode | None = None) -> SPNode | None:
        if root is None:
            root = self.project.sp_config.root
        for child in root.children:
            if child.id == node_id:
                return root
            found = self._sp_find_parent(node_id, child)
            if found:
                return found
        return None

    def _sp_target_group(self) -> SPNode:
        sel = self._sp_selected_node()
        if sel is None:
            return self.project.sp_config.root
        if sel.node_type != "component":
            return sel
        parent = self._sp_find_parent(sel.id)
        return parent if parent else self.project.sp_config.root

    def _sp_add_node(self):
        dlg = SPNodeDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_node = dlg.get_node()
            target = self._sp_target_group()
            target.children.append(new_node)
            self._refresh_sp_tree()
            self._auto_calculate()

    def _sp_add_group(self):
        node = SPNode(name="Yeni Grup", node_type="series")
        dlg = SPNodeDialog(node=node, allow_component=False, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            target = self._sp_target_group()
            target.children.append(dlg.get_node())
            self._refresh_sp_tree()
            self._auto_calculate()

    def _sp_edit_node(self):
        sel = self._sp_selected_node()
        if sel is None:
            QMessageBox.information(self, "Bilgi",
                                    "Düzenlemek için bir düğüm seçin.")
            return
        is_root = (sel.id == self.project.sp_config.root.id)
        dlg = SPNodeDialog(node=sel,
                           allow_component=(not is_root and
                                            len(sel.children) == 0),
                           parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_sp_tree()
            self._auto_calculate()

    def _sp_delete_node(self):
        sel = self._sp_selected_node()
        if sel is None:
            QMessageBox.information(self, "Bilgi",
                                    "Silmek için bir düğüm seçin.")
            return
        if sel.id == self.project.sp_config.root.id:
            QMessageBox.warning(self, "Uyarı", "Kök düğüm silinemez.")
            return
        parent = self._sp_find_parent(sel.id)
        if parent:
            reply = QMessageBox.question(
                self, "Onay", f"'{sel.name}' silinsin mi?")
            if reply == QMessageBox.StandardButton.Yes:
                parent.children.remove(sel)
                self._refresh_sp_tree()
                self._auto_calculate()

    # ── Kapı işlemleri ─────────────────────────────────────────────

    def _refresh_gate_table(self):
        ft = self.project.fault_tree
        self._gate_table.setRowCount(len(ft.gates))
        for row, (gid, gate) in enumerate(ft.gates.items()):
            children_names = []
            for cid in gate.children:
                if cid in ft.basic_events:
                    children_names.append(ft.basic_events[cid].name)
                elif cid in ft.gates:
                    children_names.append(ft.gates[cid].name)
                else:
                    children_names.append(f"?{cid}")
            type_str = gate.gate_type.value
            if gate.gate_type == GateType.VOTE:
                type_str = f"VOTE({gate.vote_k}/{len(gate.children)})"
            for col, text in enumerate([
                gid, gate.name, type_str,
                ", ".join(children_names),
            ]):
                self._gate_table.setItem(row, col, QTableWidgetItem(text))

    def _refresh_top_combo(self):
        ft = self.project.fault_tree
        self._top_combo.blockSignals(True)
        self._top_combo.clear()
        self._top_combo.addItem("— Tepe Olayı Seçin —", None)
        for gid, gate in ft.gates.items():
            self._top_combo.addItem(f"{gate.name} ({gid})", gid)
        if ft.top_event_id:
            idx = self._top_combo.findData(ft.top_event_id)
            if idx >= 0:
                self._top_combo.setCurrentIndex(idx)
        self._top_combo.blockSignals(False)

    def _selected_gate_id(self) -> str | None:
        row = self._gate_table.currentRow()
        if row < 0:
            return None
        return self._gate_table.item(row, 0).text()

    def _on_top_changed(self):
        gid = self._top_combo.currentData()
        self.project.fault_tree.top_event_id = gid
        self._auto_calculate()

    def _add_gate(self):
        ft = self.project.fault_tree
        dlg = GateDialog(None, ft.basic_events, ft.gates, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            gate = dlg.get_gate()
            ft.gates[gate.id] = gate
            self._refresh_gate_table()
            self._refresh_top_combo()
            self._auto_calculate()

    def _edit_gate(self):
        gid = self._selected_gate_id()
        if gid is None:
            QMessageBox.information(self, "Bilgi",
                                    "Düzenlemek için bir kapı seçin.")
            return
        ft = self.project.fault_tree
        dlg = GateDialog(ft.gates[gid], ft.basic_events, ft.gates,
                         exclude_id=gid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_gate_table()
            self._auto_calculate()

    def _delete_gate(self):
        gid = self._selected_gate_id()
        if gid is None:
            QMessageBox.information(self, "Bilgi",
                                    "Silmek için bir kapı seçin.")
            return
        ft = self.project.fault_tree
        reply = QMessageBox.question(
            self, "Onay", f"'{ft.gates[gid].name}' kapısı silinsin mi?")
        if reply == QMessageBox.StandardButton.Yes:
            del ft.gates[gid]
            for g in ft.gates.values():
                if gid in g.children:
                    g.children.remove(gid)
            if ft.top_event_id == gid:
                ft.top_event_id = None
            self._refresh_gate_table()
            self._refresh_top_combo()
            self._auto_calculate()

    # ── ET işlemleri ───────────────────────────────────────────────

    def _refresh_et_panel(self):
        et = self.project.event_tree
        events = self.project.fault_tree.basic_events

        self._ie_name.blockSignals(True)
        self._ie_freq.blockSignals(True)
        self._ie_name.setText(et.initiating_event_name)
        self._ie_freq.setValue(et.initiating_event_frequency)
        self._ie_name.blockSignals(False)
        self._ie_freq.blockSignals(False)

        self._branch_table.setRowCount(len(et.branches))
        for row, br in enumerate(et.branches):
            if br.basic_event_id and br.basic_event_id in events:
                source = f"Olay: {events[br.basic_event_id].name}"
                p_succ = events[br.basic_event_id].get_reliability()
            elif br.success_probability is not None:
                source = "Doğrudan"
                p_succ = br.success_probability
            else:
                source = "—"
                p_succ = 0.5
            for col, text in enumerate([br.name, source, f"{p_succ:.6f}"]):
                self._branch_table.setItem(row, col, QTableWidgetItem(text))

    def _sync_ie(self):
        et = self.project.event_tree
        et.initiating_event_name = (
            self._ie_name.text().strip() or "Başlatıcı Olay")
        et.initiating_event_frequency = self._ie_freq.value()
        self._schedule_auto_calc()

    def _add_branch(self):
        et = self.project.event_tree
        events = self.project.fault_tree.basic_events
        if len(et.branches) >= 8:
            QMessageBox.warning(
                self, "Uyarı",
                "En fazla 8 dal desteklenir (2⁸ = 256 sonuç).")
            return
        dlg = BranchDialog(None, events, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            et.branches.append(dlg.get_branch())
            self._refresh_et_panel()
            self._auto_calculate()

    def _edit_branch(self):
        row = self._branch_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Bilgi",
                                    "Düzenlemek için bir dal seçin.")
            return
        events = self.project.fault_tree.basic_events
        br = self.project.event_tree.branches[row]
        dlg = BranchDialog(br, events, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_et_panel()
            self._auto_calculate()

    def _delete_branch(self):
        row = self._branch_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Bilgi",
                                    "Silmek için bir dal seçin.")
            return
        et = self.project.event_tree
        reply = QMessageBox.question(
            self, "Onay", f"'{et.branches[row].name}' dalı silinsin mi?")
        if reply == QMessageBox.StandardButton.Yes:
            et.branches.pop(row)
            self._refresh_et_panel()
            self._auto_calculate()

    def _move_branch_up(self):
        row = self._branch_table.currentRow()
        if row <= 0:
            return
        branches = self.project.event_tree.branches
        branches[row], branches[row - 1] = branches[row - 1], branches[row]
        self._refresh_et_panel()
        self._branch_table.selectRow(row - 1)
        self._auto_calculate()

    def _move_branch_down(self):
        row = self._branch_table.currentRow()
        branches = self.project.event_tree.branches
        if row < 0 or row >= len(branches) - 1:
            return
        branches[row], branches[row + 1] = branches[row + 1], branches[row]
        self._refresh_et_panel()
        self._branch_table.selectRow(row + 1)
        self._auto_calculate()

    def _on_outcome_label_changed(self, row: int, col: int):
        if col != 4:
            return
        et = self.project.event_tree
        text = self._outcome_table.item(row, 4).text()
        while len(et.outcome_labels) <= row:
            et.outcome_labels.append("")
        et.outcome_labels[row] = text

    # ── Proje işlemleri ────────────────────────────────────────────

    def _update_title(self):
        name = (os.path.basename(self._current_file)
                if self._current_file else "Adsız")
        self.setWindowTitle(f"HÖA Analizörü — {name}")

    def _new_project(self):
        reply = QMessageBox.question(
            self, "Yeni Proje",
            "Mevcut proje silinip yeni proje oluşturulsun mu?")
        if reply == QMessageBox.StandardButton.Yes:
            self.project = Project()
            self._current_file = None
            self._ft_results = None
            self._et_outcomes = None
            self._set_mode(self._current_mode)
            self._update_title()
            self.statusBar().showMessage("Yeni proje oluşturuldu.")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Proje Aç", "",
            "JSON Dosyaları (*.json);;Tüm Dosyalar (*)")
        if path:
            self._load_file(path)

    def _save_project(self):
        if self._current_file:
            self._do_save(self._current_file)
        else:
            self._save_as_project()

    def _save_as_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Projeyi Kaydet", "proje.json",
            "JSON Dosyaları (*.json);;Tüm Dosyalar (*)")
        if path:
            self._do_save(path)

    def _do_save(self, path: str):
        try:
            self.project.save(path)
            self._current_file = path
            self._update_title()
            self.statusBar().showMessage(f"Proje kaydedildi: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")

    def _load_file(self, path: str):
        try:
            self.project = Project.load(path)
            self._current_file = path
            self._ft_results = None
            self._et_outcomes = None
            self._update_title()
            self.statusBar().showMessage(f"Proje yüklendi: {path}")

            has_ft = bool(self.project.fault_tree.gates)
            has_et = bool(self.project.event_tree.branches)
            has_sp = bool(self.project.sp_config.root.children)

            if has_ft:
                self._set_mode(self.MODE_FT)
            elif has_et:
                self._set_mode(self.MODE_ET)
            elif has_sp:
                self._set_mode(self.MODE_SP)
            else:
                self._set_mode(self._current_mode)

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Yüklenemedi:\n{e}")

    # ── PDF Rapor ─────────────────────────────────────────────

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "PDF Rapor Kaydet", "rapor.pdf",
            "PDF Dosyaları (*.pdf);;Tüm Dosyalar (*)")
        if not path:
            return
        try:
            self._generate_pdf(path)
            self.statusBar().showMessage(f"PDF rapor oluşturuldu: {path}")
            QMessageBox.information(self, "Başarılı",
                                    f"Rapor kaydedildi:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata",
                                 f"PDF oluşturulamadı:\n{e}")

    def _generate_pdf(self, path: str):
        from fpdf import FPDF
        from datetime import datetime

        FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_font("dejavu", "", FONT_DIR + "DejaVuSans.ttf")
        pdf.add_font("dejavu", "B", FONT_DIR + "DejaVuSans-Bold.ttf")
        pdf.add_font("mono", "", FONT_DIR + "DejaVuSansMono.ttf")
        pdf.add_font("mono", "B", FONT_DIR + "DejaVuSansMono-Bold.ttf")

        def title(text):
            pdf.set_font("dejavu", "B", 14)
            pdf.set_fill_color(25, 118, 210)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT", fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(3)

        def subtitle(text):
            pdf.set_font("dejavu", "B", 11)
            pdf.set_text_color(25, 118, 210)
            pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

        def text(t, size=9):
            pdf.set_font("dejavu", "", size)
            pdf.multi_cell(0, 5, t)
            pdf.ln(1)

        def mono(t, size=8):
            pdf.set_font("mono", "", size)
            pdf.multi_cell(0, 4.5, t)
            pdf.ln(1)

        # Kapak sayfası
        pdf.add_page()
        pdf.ln(40)
        pdf.set_font("dejavu", "B", 24)
        pdf.cell(0, 15, "HÖA Analiz Raporu", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        pdf.set_font("dejavu", "", 12)
        pdf.cell(0, 8, f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        mode_names = ["Seri/Paralel Analizi", "Hata Ağacı Analizi",
                      "Olay Ağacı Analizi"]
        pdf.cell(0, 8, f"Analiz Türü: {mode_names[self._current_mode]}",
                 align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.add_page()

        if self._current_mode == self.MODE_FT:
            self._pdf_ft(pdf, title, subtitle, text, mono)
        elif self._current_mode == self.MODE_ET:
            self._pdf_et(pdf, title, subtitle, text, mono)
        elif self._current_mode == self.MODE_SP:
            self._pdf_sp(pdf, title, subtitle, text, mono)

        if self._last_diagram_path and os.path.exists(self._last_diagram_path):
            pdf.add_page("L")
            title("Diyagram")
            try:
                img_w = pdf.epw
                pdf.image(self._last_diagram_path, x=pdf.l_margin,
                          w=img_w)
            except Exception:
                text("Diyagram eklenemedi.")

        pdf.output(path)

    def _pdf_ft(self, pdf, title, subtitle, text, mono):
        ft = self.project.fault_tree
        title("HATA AĞACI ANALİZİ")

        subtitle("Temel Olaylar")
        header = f"  {'Ad':<24s} {'Mod':<10s} {'R':>12s} {'F':>12s}"
        lines = [header, "  " + "-" * 60]
        for ev in ft.basic_events.values():
            mode = "λt" if ev.use_time_dependent else "Doğrudan"
            r = ev.get_reliability()
            f = ev.get_failure_probability()
            lines.append(f"  {ev.name:<24s} {mode:<10s} {r:>12.6e} {f:>12.6e}")
        mono("\n".join(lines))

        subtitle("Mantık Kapıları")
        for gid, gate in ft.gates.items():
            children_names = []
            for cid in gate.children:
                if cid in ft.basic_events:
                    children_names.append(ft.basic_events[cid].name)
                elif cid in ft.gates:
                    children_names.append(ft.gates[cid].name)
            marker = " (TEPE OLAY)" if gid == ft.top_event_id else ""
            text(f"{gate.name}{marker}  [{gate.gate_type.value}]: "
                 f"{', '.join(children_names)}")

        if ft.top_event_id and self._ft_results:
            top = self._ft_results.get("_top_event", {})
            if top.get("failure_probability") is not None:
                subtitle("Tepe Olay Sonucu")
                mono(f"  Arıza Olasılığı (F) = {top['failure_probability']:.6e}\n"
                     f"  Güvenilirlik (R)    = {top['reliability']:.6e}")

        mcs_engine = MinimalCutSetEngine(ft)
        mcs_list = mcs_engine.calculate()
        if mcs_list:
            mcs_probs = mcs_engine.mcs_probabilities(mcs_list)
            subtitle(f"Minimal Kesim Kümeleri (MCS) — Toplam: {len(mcs_list)}")
            lines = []
            for i, (mcs, prob) in enumerate(mcs_probs, 1):
                names = sorted(ft.basic_events[eid].name for eid in mcs
                               if eid in ft.basic_events)
                lines.append(f"  MCS-{i:02d} ({len(mcs)}. derece): "
                             f"{' ∩ '.join(names)}  P = {prob:.6e}")
            mono("\n".join(lines))

        imp_engine = ImportanceMeasures(ft)
        imp_results = imp_engine.calculate()
        if imp_results:
            subtitle("Önem Ölçüleri")
            hdr = f"  {'Olay':<22s} {'Birnbaum':>10s} {'FV':>8s} {'RAW':>8s} {'RRW':>8s}"
            lines = [hdr, "  " + "-" * 58]
            for eid, vals in sorted(imp_results.items(),
                                    key=lambda x: x[1]["fussell_vesely"],
                                    reverse=True):
                ev = ft.basic_events.get(eid)
                name = (ev.name if ev else eid)[:22]
                rrw_s = f"{vals['rrw']:8.4f}" if vals['rrw'] != float('inf') else "     ∞"
                lines.append(f"  {name:<22s} {vals['birnbaum']:10.4e}"
                             f" {vals['fussell_vesely']:8.4f}"
                             f" {vals['raw']:8.4f}{rrw_s}")
            mono("\n".join(lines))

    def _pdf_et(self, pdf, title, subtitle, text, mono):
        et = self.project.event_tree
        title("OLAY AĞACI ANALİZİ")

        subtitle("Başlatıcı Olay")
        text(f"Ad: {et.initiating_event_name}\n"
             f"Frekans: {et.initiating_event_frequency:.6e}")

        subtitle("Dallar (Güvenlik Sistemleri)")
        events = self.project.fault_tree.basic_events
        for br in et.branches:
            if br.basic_event_id and br.basic_event_id in events:
                p = events[br.basic_event_id].get_reliability()
                src = f"Olay: {events[br.basic_event_id].name}"
            elif br.success_probability is not None:
                p = br.success_probability
                src = "Doğrudan"
            else:
                p = 0.5
                src = "Varsayılan"
            text(f"  {br.name}: P(başarı) = {p:.6f}  ({src})")

        if self._et_outcomes:
            subtitle(f"Sonuç Dizileri — Toplam: {len(self._et_outcomes)}")
            lines = []
            for i, oc in enumerate(self._et_outcomes):
                seq = " → ".join(f"{n}:{s[0]}" for n, s in oc["sequence"])
                label = ""
                if i < len(et.outcome_labels) and et.outcome_labels[i]:
                    label = f"  [{et.outcome_labels[i]}]"
                lines.append(f"  #{i+1:3d}  P={oc['probability']:.4e}"
                             f"  Freq={oc['frequency']:.4e}{label}")
                lines.append(f"        {seq}")
            mono("\n".join(lines))

    def _pdf_sp(self, pdf, title, subtitle, text, mono):
        root = self.project.sp_config.root
        title("SERİ-PARALEL SİSTEM ANALİZİ")

        r_sys = root.calc_reliability()
        subtitle("Sistem Sonucu")
        mono(f"  Sistem Güvenilirliği:    R = {r_sys:.8e}\n"
             f"  Sistem Arıza Olasılığı: F = {1.0 - r_sys:.8e}")

        subtitle("Sistem Yapısı")
        lines = self._sp_node_text(root, indent=1)
        mono("\n".join(lines))

    # ── Örnek projeler ──────────────────────────────────────────

    def _load_example(self, project: Project, mode: int, title: str,
                      explanation: str = ""):
        self.project = project
        self._current_file = None
        self._ft_results = None
        self._et_outcomes = None
        self._update_title()
        self._set_mode(mode)
        self.statusBar().showMessage(f"Örnek yüklendi: {title}")
        if explanation:
            self._show_example_explanation(title, explanation)

    def _show_example_explanation(self, title: str, html: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Örnek Açıklaması — {title}")
        dlg.resize(750, 550)
        layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Sans", 10))
        text.setStyleSheet("QTextEdit { background-color: #ffffff; color: #222222; }")
        text.setHtml(html)
        layout.addWidget(text)

        btn = QPushButton("Anladım, Kapat")
        btn.setStyleSheet(
            "background-color: #1976D2; color: white; "
            "padding: 8px 24px; font-weight: bold; border-radius: 4px;")
        btn.clicked.connect(dlg.close)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _example_redundant_pump(self):
        proj = Project()
        ft = proj.fault_tree
        ft.name = "Redundant Pompa Sistemi"

        e1 = BasicEvent(id="pa", name="Pompa A Arızası", reliability=0.99)
        e2 = BasicEvent(id="pb", name="Pompa B Arızası", reliability=0.98)
        e3 = BasicEvent(id="va", name="Vana Arızası", reliability=0.95)
        e4 = BasicEvent(id="gk", name="Güç Kaybı", reliability=0.999)
        e5 = BasicEvent(id="kh", name="Kontrol Hatası", reliability=0.997)
        ft.basic_events = {e.id: e for e in [e1, e2, e3, e4, e5]}

        g1 = Gate(id="g_pompa", name="Tüm Pompalar Arızalı",
                  gate_type=GateType.AND, children=["pa", "pb"])
        g2 = Gate(id="g_destek", name="Destek Sistemi Arızası",
                  gate_type=GateType.OR, children=["gk", "kh"])
        g3 = Gate(id="g_sog", name="Soğutma Kaybı",
                  gate_type=GateType.OR, children=["g_pompa", "va"])
        g_top = Gate(id="g_top", name="Sistem Arızası",
                     gate_type=GateType.OR, children=["g_sog", "g_destek"])
        ft.gates = {g.id: g for g in [g1, g2, g3, g_top]}
        ft.top_event_id = "g_top"

        self._load_example(proj, self.MODE_FT, "Redundant Pompa Sistemi", """
        <h2 style="color:#1565C0;">Redundant Pompa Sistemi — Hata Ağacı</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Bir soğutma sisteminde iki pompa (<b>A</b> ve <b>B</b>) paralel
        (yedekli) çalışmaktadır. Ayrıca bir <b>vana</b> ve bir <b>destek
        sistemi</b> (güç + kontrol) bulunur.</p>

        <h3>Ağaç Yapısı (Yukarıdan Aşağı)</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#FFCDD2;">
            <td style="border:1px solid #ccc;"><b>Sistem Arızası</b> (TEPE — OR)</td>
            <td style="border:1px solid #ccc;">Soğutma VEYA destek sistemi arızalanırsa
            sistem durur</td></tr>
        <tr style="background:#FFF9C4;">
            <td style="border:1px solid #ccc;">├─ <b>Soğutma Kaybı</b> (OR)</td>
            <td style="border:1px solid #ccc;">Pompalar VEYA vana arızalanırsa soğutma
            kaybolur</td></tr>
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;">│ ├─ <b>Tüm Pompalar Arızalı</b> (AND)</td>
            <td style="border:1px solid #ccc;">İki pompa da arızalanmalı (yedeklilik).<br>
            F = F(A) × F(B) = 0.01 × 0.02 = <b>0.0002</b></td></tr>
        <tr>
            <td style="border:1px solid #ccc;">│ └─ Vana Arızası</td>
            <td style="border:1px solid #ccc;">F = 0.05 — tek başına bir MCS</td></tr>
        <tr style="background:#FFF9C4;">
            <td style="border:1px solid #ccc;">└─ <b>Destek Sistemi Arızası</b> (OR)</td>
            <td style="border:1px solid #ccc;">Güç VEYA kontrol hatası</td></tr>
        </table>

        <h3>Neden Böyle Kuruldu?</h3>
        <ul>
        <li><b>AND kapısı</b> (pompalar): İki pompa yedekli çalıştığı için
        <i>ikisi de</i> arızalanmalı → olasılık çok düşer (çarpım)</li>
        <li><b>OR kapısı</b> (soğutma): Pompa grubu veya vana — <i>herhangi biri</i>
        yetecektir → olasılık yükselir (toplam)</li>
        </ul>

        <h3>Beklenen Sonuçlar</h3>
        <ul>
        <li><b>MCS:</b> {Vana}, {Güç Kaybı}, {Kontrol Hatası},
        {Pompa A ∩ Pompa B} — Vana en kritik çünkü tek başına bir MCS</li>
        <li><b>FV değerleri:</b> Vana ≈ %92 (en yüksek), pompalar ≈ %0.4</li>
        <li><b>Yorum:</b> Vanayı iyileştirmek sistemi en çok güçlendirir</li>
        </ul>
        """)

    def _example_loca_et(self):
        proj = Project()

        ev_trip = BasicEvent(id="ev_trip", name="Reaktör Trip Başarısızlığı",
                             reliability=0.999)
        ev_eccs = BasicEvent(id="ev_eccs", name="ECCS Enjeksiyon Arızası",
                             reliability=0.99)
        ev_kont = BasicEvent(id="ev_kont", name="Konteyment Yalıtım Kaybı",
                             reliability=0.995)
        ev_uvs = BasicEvent(id="ev_uvs", name="Uzun Vadeli Soğutma Arızası",
                            reliability=0.98)
        for ev in (ev_trip, ev_eccs, ev_kont, ev_uvs):
            proj.fault_tree.basic_events[ev.id] = ev

        et = proj.event_tree
        et.name = "Büyük LOCA Olay Ağacı"
        et.initiating_event_name = "Büyük Boru Kırılması (LOCA)"
        et.initiating_event_frequency = 1e-4

        b1 = EventTreeBranch(id="b1", name="Reaktör Trip",
                             basic_event_id="ev_trip",
                             success_probability=0.999)
        b2 = EventTreeBranch(id="b2", name="ECCS Enjeksiyonu",
                             basic_event_id="ev_eccs",
                             success_probability=0.99)
        b3 = EventTreeBranch(id="b3", name="Konteyment Yalıtımı",
                             basic_event_id="ev_kont",
                             success_probability=0.995)
        b4 = EventTreeBranch(id="b4", name="Uzun Vadeli Soğutma",
                             basic_event_id="ev_uvs",
                             success_probability=0.98)
        et.branches = [b1, b2, b3, b4]
        et.outcome_labels = [
            "Güvenli Duruş",
            "Geç Dönem Soğutma Kaybı",
            "Konteyment Sızıntısı",
            "Konteyment + Soğutma Kaybı",
            "ECCS Başarısız — Soğutma Var",
            "ECCS + Soğutma Kaybı",
            "ECCS + Konteyment Kaybı",
            "Tam Erime (Kör Arıza)",
            "Trip Başarısız — Soğutma Var",
            "Trip + Soğutma Kaybı",
            "Trip + Konteyment Kaybı",
            "Trip + Konteyment + Soğutma Kaybı",
            "Trip + ECCS Kaybı",
            "Trip + ECCS + Soğutma Kaybı",
            "Trip + ECCS + Konteyment Kaybı",
            "Toplam Kayıp",
        ]

        self._load_example(proj, self.MODE_ET, "Büyük LOCA Olay Ağacı", """
        <h2 style="color:#E65100;">Büyük LOCA — Olay Ağacı</h2>
        <hr>

        <h3>Senaryo</h3>
        <p>Nükleer reaktörde birincil soğutma devresinde <b>büyük bir boru
        kırılması (LOCA)</b> meydana gelir. Başlatıcı olay frekansı:
        <b>10⁻⁴ / yıl</b>.</p>

        <h3>Güvenlik Bariyerleri (Soldan Sağa)</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;"><b>1. Reaktör Trip</b></td>
            <td style="border:1px solid #ccc;">Kontrol çubukları düşerek zincirleme
            reaksiyonu durdurur. P(başarı) = 0.999</td></tr>
        <tr>
            <td style="border:1px solid #ccc;"><b>2. ECCS Enjeksiyonu</b></td>
            <td style="border:1px solid #ccc;">Acil çekirdek soğutma sistemi devreye
            girer. P(başarı) = 0.99</td></tr>
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;"><b>3. Konteyment Yalıtımı</b></td>
            <td style="border:1px solid #ccc;">Konteyment binası radyoaktif sızıntıyı
            engeller. P(başarı) = 0.995</td></tr>
        <tr>
            <td style="border:1px solid #ccc;"><b>4. Uzun Vadeli Soğutma</b></td>
            <td style="border:1px solid #ccc;">Saatler/günler boyunca artık ısıyı
            uzaklaştırır. P(başarı) = 0.98</td></tr>
        </table>

        <h3>Nasıl Hesaplanır?</h3>
        <ul>
        <li>4 dal → 2⁴ = <b>16 sonuç dizisi</b></li>
        <li>Her sonucun olasılığı = dallar boyunca P'lerin çarpımı</li>
        <li>Örnek: Tümü başarılı → 0.999 × 0.99 × 0.995 × 0.98 ≈ <b>0.964</b></li>
        <li>Frekans = Başlatıcı frekans × Olasılık → 10⁻⁴ × 0.964 ≈ <b>9.64×10⁻⁵</b></li>
        <li>En kötü senaryo (tümü başarısız): frekans ≈ 10⁻⁴ × 10⁻⁹ ≈ <b>10⁻¹³</b></li>
        </ul>

        <h3>Yorum</h3>
        <p>Tabloda yeşil satırlar güvenli, sarı kısmen tehlikeli, kırmızı en
        kötü senaryolardır. Etiketler sonucu tanımlar.</p>
        """)

    def _example_power_supply_sp(self):
        proj = Project()
        root = proj.sp_config.root
        root.name = "Güç Kaynağı Sistemi"
        root.node_type = "series"

        trafo = SPNode(name="Transformatör", node_type="component",
                       reliability=0.995)
        rectifier_group = SPNode(name="Redresör Grubu", node_type="parallel")
        rectifier_group.children = [
            SPNode(name="Redresör 1", node_type="component", reliability=0.97),
            SPNode(name="Redresör 2", node_type="component", reliability=0.97),
        ]
        battery = SPNode(name="Akü Bankası", node_type="parallel")
        battery.children = [
            SPNode(name="Akü Grubu A", node_type="component", reliability=0.99),
            SPNode(name="Akü Grubu B", node_type="component", reliability=0.99),
        ]
        inverter = SPNode(name="İnvertör", node_type="component",
                          reliability=0.98)

        root.children = [trafo, rectifier_group, battery, inverter]

        self._load_example(proj, self.MODE_SP, "Güç Kaynağı Sistemi", """
        <h2 style="color:#1565C0;">Güç Kaynağı Sistemi — Seri/Paralel</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Kesintisiz güç kaynağı (UPS) sistemi dört ana bloktan oluşur ve
        bunlar <b>seri</b> bağlıdır — herhangi biri arızalanırsa güç kesilir.</p>

        <h3>Sistem Yapısı</h3>
        <pre style="background:#f5f5f5; padding:10px; border-radius:4px;">
  Giriş ─→ [Transformatör] ─→ [Redresör 1 ║ Redresör 2] ─→ [Akü A ║ Akü B] ─→ [İnvertör] ─→ Çıkış
              R=0.995          Paralel (yedekli)           Paralel (yedekli)      R=0.98
        </pre>

        <h3>Nasıl Hesaplanır?</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#FFF9C4;">
            <td style="border:1px solid #ccc;"><b>Paralel blok</b></td>
            <td style="border:1px solid #ccc;">
            R = 1 − (1−R₁)(1−R₂)<br>
            Redresör: R = 1 − (0.03)(0.03) = 1 − 0.0009 = <b>0.9991</b><br>
            Akü: R = 1 − (0.01)(0.01) = 1 − 0.0001 = <b>0.9999</b></td></tr>
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;"><b>Seri (tüm sistem)</b></td>
            <td style="border:1px solid #ccc;">
            R<sub>sis</sub> = R₁ × R₂ × R₃ × R₄<br>
            = 0.995 × 0.9991 × 0.9999 × 0.98 ≈ <b>0.9741</b></td></tr>
        </table>

        <h3>Yorum</h3>
        <ul>
        <li>Paralel (yedekli) bloklar güvenilirliği çok artırır (0.97 → 0.9991)</li>
        <li>Seri bağlı tek bileşenler (Trafo, İnvertör) zincirin zayıf halkasıdır</li>
        <li>En büyük iyileştirme İnvertöre yedek eklemekle sağlanır</li>
        </ul>
        """)

    def _example_fire_safety(self):
        """Basit yangın güvenlik sistemi — hocanın kolayca takip edeceği 2 kapılı FTA."""
        proj = Project()
        ft = proj.fault_tree
        ft.name = "Yangın Güvenlik Sistemi Arızası"

        e1 = BasicEvent(id="dd", name="Dedektör Arızası", reliability=0.98)
        e2 = BasicEvent(id="al", name="Alarm Arızası", reliability=0.995)
        e3 = BasicEvent(id="sp", name="Sprinkler Arızası", reliability=0.97)
        e4 = BasicEvent(id="ym", name="Yangın Müd. Gecikmesi", reliability=0.99)
        ft.basic_events = {e.id: e for e in [e1, e2, e3, e4]}

        g1 = Gate(id="g_tespit", name="Tespit Başarısız",
                  gate_type=GateType.AND, children=["dd", "al"])
        g2 = Gate(id="g_top", name="Yangın Koruması Kaybı",
                  gate_type=GateType.OR, children=["g_tespit", "sp", "ym"])
        ft.gates = {g.id: g for g in [g1, g2]}
        ft.top_event_id = "g_top"

        self._load_example(proj, self.MODE_FT, "Yangın Güvenlik Sistemi", """
        <h2 style="color:#B71C1C;">Yangın Güvenlik Sistemi — Hata Ağacı</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Bir binanın yangın koruması üç katmandan oluşur: <b>tespit</b>
        (dedektör + alarm), <b>söndürme</b> (sprinkler), <b>müdahale</b>
        (itfaiye/personel). Basit ve anlaşılır bir FTA örneğidir.</p>

        <h3>Ağaç Yapısı</h3>
        <pre style="background:#f5f5f5; padding:10px; border-radius:4px;">
  Yangın Koruması Kaybı (OR) ← TEPE OLAY
    ├── Tespit Başarısız (AND)
    │     ├── Dedektör Arızası  F=0.02
    │     └── Alarm Arızası     F=0.005
    ├── Sprinkler Arızası       F=0.03
    └── Yangın Müd. Gecikmesi   F=0.01
        </pre>

        <h3>Neden AND ve OR?</h3>
        <ul>
        <li><b>AND (Tespit):</b> Dedektör ve alarm <i>ikisi de</i> başarısız
        olmalı ki tespit yapılamasın. Yedeklilik var → çarpım → çok düşük
        olasılık: 0.02 × 0.005 = <b>0.0001</b></li>
        <li><b>OR (Tepe):</b> Tespit, sprinkler veya müdahaleden <i>herhangi
        birinin</i> başarısızlığı yeterli → olasılıklar toplanır</li>
        </ul>

        <h3>Beklenen Sonuçlar</h3>
        <ul>
        <li><b>MCS:</b> {Sprinkler}, {Müdahale Gecikmesi},
        {Dedektör ∩ Alarm} — üç MCS</li>
        <li>Sprinkler en kritik bileşen (FV en yüksek)</li>
        <li>AND kapısı sayesinde tespit katmanı çok güvenilir</li>
        </ul>
        """)

    def _example_diesel_vote(self):
        """Acil dizel jeneratör sistemi — 3 jeneratörden en az 2'si çalışmalı (VOTE 2/3)."""
        proj = Project()
        ft = proj.fault_tree
        ft.name = "Acil Dizel Jeneratör Sistemi"

        e1 = BasicEvent(id="dg1", name="Dizel Jen. 1 Arızası", reliability=0.97)
        e2 = BasicEvent(id="dg2", name="Dizel Jen. 2 Arızası", reliability=0.97)
        e3 = BasicEvent(id="dg3", name="Dizel Jen. 3 Arızası", reliability=0.97)
        e4 = BasicEvent(id="yks", name="Yakıt Sistemi Arızası", reliability=0.999)
        e5 = BasicEvent(id="oto", name="Otostart Arızası", reliability=0.995)
        ft.basic_events = {e.id: e for e in [e1, e2, e3, e4, e5]}

        g1 = Gate(id="g_vote", name="≥2 Jeneratör Arızalı",
                  gate_type=GateType.VOTE, children=["dg1", "dg2", "dg3"],
                  vote_k=2)
        g2 = Gate(id="g_destek", name="Destek Sistemi Arızası",
                  gate_type=GateType.OR, children=["yks", "oto"])
        g_top = Gate(id="g_top", name="Acil Güç Kaybı",
                     gate_type=GateType.OR, children=["g_vote", "g_destek"])
        ft.gates = {g.id: g for g in [g1, g2, g_top]}
        ft.top_event_id = "g_top"

        self._load_example(proj, self.MODE_FT, "Acil Dizel Jeneratör (VOTE 2/3)", """
        <h2 style="color:#6A1B9A;">Acil Dizel Jeneratör — VOTE (k/n) Kapısı</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Nükleer santralde şebeke elektriği kesildiğinde 3 dizel jeneratör
        devreye girer. Güvenlik sistemleri için <b>en az 2 jeneratör</b>
        çalışmalıdır (2-out-of-3 = VOTE 2/3).</p>

        <h3>VOTE Kapısı Nedir?</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#F3E5F5;">
            <td style="border:1px solid #ccc;"><b>AND</b></td>
            <td style="border:1px solid #ccc;">Tüm n eleman arızalanmalı (n/n)</td></tr>
        <tr style="background:#EDE7F6;">
            <td style="border:1px solid #ccc;"><b>OR</b></td>
            <td style="border:1px solid #ccc;">1 eleman yeterli (1/n)</td></tr>
        <tr style="background:#E1BEE7;">
            <td style="border:1px solid #ccc;"><b>VOTE k/n</b></td>
            <td style="border:1px solid #ccc;">En az k eleman arızalanmalı (genel durum)</td></tr>
        </table>

        <h3>Hesaplama</h3>
        <p>3 jeneratör, her birinin F = 0.03:</p>
        <ul>
        <li>Tam 2 arıza: C(3,2) × 0.03² × 0.97 = 3 × 0.0009 × 0.97 = <b>0.002619</b></li>
        <li>3 arıza: 0.03³ = <b>0.000027</b></li>
        <li>VOTE 2/3 toplam: <b>0.002646</b></li>
        </ul>

        <h3>MCS Sonuçları</h3>
        <p>3 tane 2. derece MCS: {DG1 ∩ DG2}, {DG1 ∩ DG3}, {DG2 ∩ DG3}</p>
        <p>AND olsaydı tek 3. derece MCS olurdu; OR olsaydı 3 tane 1. derece MCS.</p>
        """)

    def _example_nuclear_cooling(self):
        """Nükleer reaktör soğutma kaybı — çok katmanlı FTA."""
        proj = Project()
        ft = proj.fault_tree
        ft.name = "Reaktör Soğutma Kaybı"

        events = [
            BasicEvent(id="pa", name="Ana Pompa A", reliability=0.995),
            BasicEvent(id="pb", name="Ana Pompa B", reliability=0.995),
            BasicEvent(id="ha", name="Isı Değ. A Tıkanma", reliability=0.998),
            BasicEvent(id="hb", name="Isı Değ. B Tıkanma", reliability=0.998),
            BasicEvent(id="cv", name="Kontrol Vanası", reliability=0.99),
            BasicEvent(id="sn", name="Sensör Hatası", reliability=0.999),
            BasicEvent(id="ep", name="Acil Pompa", reliability=0.98),
        ]
        ft.basic_events = {e.id: e for e in events}

        g1 = Gate(id="g_pump", name="Tüm Ana Pompalar Durdu",
                  gate_type=GateType.AND, children=["pa", "pb"])
        g2 = Gate(id="g_hx", name="Tüm Isı Değ. Tıkandı",
                  gate_type=GateType.AND, children=["ha", "hb"])
        g3 = Gate(id="g_normal", name="Normal Soğutma Kaybı",
                  gate_type=GateType.OR, children=["g_pump", "g_hx", "cv"])
        g4 = Gate(id="g_kontrol", name="Kontrol Sistemi Arızası",
                  gate_type=GateType.OR, children=["sn"])
        g5 = Gate(id="g_top", name="Soğutma Fonksiyonu Kaybı",
                  gate_type=GateType.AND, children=["g_normal", "ep"])
        ft.gates = {g.id: g for g in [g1, g2, g3, g4, g5]}
        ft.top_event_id = "g_top"

        self._load_example(proj, self.MODE_FT, "Reaktör Soğutma Kaybı", """
        <h2 style="color:#B71C1C;">Reaktör Soğutma Kaybı — Çok Katmanlı FTA</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Reaktör soğutma sistemi birden fazla savunma katmanına sahiptir:
        <b>normal soğutma</b> (pompalar + ısı değiştiriciler + vana) ve
        <b>acil pompa</b>. Sistem ancak normal soğutma kaybedilir VE acil
        pompa da çalışmazsa arızalanır.</p>

        <h3>Ağaç Yapısı</h3>
        <pre style="background:#f5f5f5; padding:10px; border-radius:4px;">
  Soğutma Fonksiyonu Kaybı (AND) ← TEPE
    ├── Normal Soğutma Kaybı (OR)
    │     ├── Tüm Ana Pompalar Durdu (AND)
    │     │     ├── Ana Pompa A   F=0.005
    │     │     └── Ana Pompa B   F=0.005
    │     ├── Tüm Isı Değ. Tıkandı (AND)
    │     │     ├── Isı Değ. A    F=0.002
    │     │     └── Isı Değ. B    F=0.002
    │     └── Kontrol Vanası      F=0.01
    └── Acil Pompa                F=0.02
        </pre>

        <h3>Savunma Derinliği (Defence in Depth)</h3>
        <ul>
        <li><b>1. katman:</b> İki redundant pompa (AND) — ikisi de durmalı</li>
        <li><b>2. katman:</b> İki redundant ısı değiştirici (AND)</li>
        <li><b>3. katman:</b> Acil pompa — normal soğutma kaybolsa bile devreye girer</li>
        <li><b>Tepe AND:</b> Normal soğutma VE acil pompa birlikte arızalanmalı</li>
        </ul>

        <h3>Yorum</h3>
        <p>Tepe AND kapısı sayesinde sistem çok güvenilir. Acil pompanın
        FV değeri yüksektir çünkü son savunma hattıdır.</p>
        """)

    def _example_chemical_et(self):
        """Kimyasal tesis sızıntı senaryosu — ETA."""
        proj = Project()

        ev_tespit = BasicEvent(id="ev_tespit", name="Sızıntı Sensörü Arızası",
                               reliability=0.98)
        ev_vana = BasicEvent(id="ev_vana", name="Otomatik Vana Arızası",
                             reliability=0.95)
        ev_havuz = BasicEvent(id="ev_havuz", name="Havuzlama Sistemi Arızası",
                              reliability=0.99)
        for ev in (ev_tespit, ev_vana, ev_havuz):
            proj.fault_tree.basic_events[ev.id] = ev

        et = proj.event_tree
        et.name = "Kimyasal Tesis Sızıntı Senaryosu"
        et.initiating_event_name = "Tank Sızıntısı"
        et.initiating_event_frequency = 5e-3

        et.branches = [
            EventTreeBranch(id="b1", name="Sızıntı Tespiti",
                            basic_event_id="ev_tespit",
                            success_probability=0.98),
            EventTreeBranch(id="b2", name="Otomatik Vana Kapanma",
                            basic_event_id="ev_vana",
                            success_probability=0.95),
            EventTreeBranch(id="b3", name="Havuzlama Sistemi",
                            basic_event_id="ev_havuz",
                            success_probability=0.99),
        ]
        et.outcome_labels = [
            "Güvenli — Sızıntı Kontrol Altında",
            "Sınırlı Yayılma",
            "Vana Açık — Havuz Dolu",
            "Vana Açık — Çevreye Yayılma",
            "Tespit Yok — Havuz Çalışıyor",
            "Tespit Yok — Sınırlı Yayılma",
            "Tespit Yok — Vana Açık — Havuz",
            "En Kötü Senaryo — Tam Yayılma",
        ]

        self._load_example(proj, self.MODE_ET, "Kimyasal Tesis Sızıntısı", """
        <h2 style="color:#E65100;">Kimyasal Tesis Sızıntısı — Olay Ağacı</h2>
        <hr>

        <h3>Senaryo</h3>
        <p>Kimyasal depolama tankından sızıntı başlar.
        Frekans: <b>5×10⁻³ / yıl</b> (LOCA'dan daha sık ama daha az
        şiddetli). Üç güvenlik bariyeri sırayla devreye girer.</p>

        <h3>Güvenlik Bariyerleri</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#FFF3E0;">
            <td style="border:1px solid #ccc;"><b>1. Sızıntı Tespiti</b></td>
            <td style="border:1px solid #ccc;">Gaz/sıvı sensörleri sızıntıyı
            algılar. P(S) = 0.98</td></tr>
        <tr>
            <td style="border:1px solid #ccc;"><b>2. Otomatik Vana</b></td>
            <td style="border:1px solid #ccc;">Tespit edilince vana kapanarak
            akışı durdurur. P(S) = 0.95</td></tr>
        <tr style="background:#FFF3E0;">
            <td style="border:1px solid #ccc;"><b>3. Havuzlama</b></td>
            <td style="border:1px solid #ccc;">Sızan madde çevreye yayılmadan
            toplama havuzunda tutulur. P(S) = 0.99</td></tr>
        </table>

        <h3>Hesaplama</h3>
        <ul>
        <li>3 dal → 2³ = <b>8 sonuç</b></li>
        <li>En iyi: tümü başarılı → 0.98 × 0.95 × 0.99 = <b>0.921</b></li>
        <li>En kötü: tümü başarısız → 0.02 × 0.05 × 0.01 = <b>10⁻⁵</b></li>
        <li>En kötü frekans: 5×10⁻³ × 10⁻⁵ = <b>5×10⁻⁸ / yıl</b></li>
        </ul>

        <h3>Yorum</h3>
        <p>Bariyerlerin sırası önemlidir — ilk bariyer başarısız olursa
        sonraki bariyerlerin yükü artar. Etiketler sonuçların ciddiyetini
        gösterir.</p>
        """)

    def _example_pump_station_sp(self):
        """Su pompalama istasyonu — iç içe seri/paralel yapı."""
        proj = Project()
        root = proj.sp_config.root
        root.name = "Pompalama İstasyonu"
        root.node_type = "series"

        intake = SPNode(name="Su Giriş Vanası", node_type="component",
                        reliability=0.998)
        pump_group = SPNode(name="Pompa Grubu", node_type="parallel")
        pump_group.children = [
            SPNode(name="Pompa 1", node_type="component", reliability=0.94),
            SPNode(name="Pompa 2", node_type="component", reliability=0.94),
            SPNode(name="Pompa 3 (Yedek)", node_type="component",
                   reliability=0.94),
        ]
        filter_sys = SPNode(name="Filtreleme", node_type="series")
        filter_sys.children = [
            SPNode(name="Kaba Filtre", node_type="component", reliability=0.99),
            SPNode(name="İnce Filtre", node_type="component", reliability=0.98),
        ]
        control = SPNode(name="Kontrol Sistemi", node_type="parallel")
        control.children = [
            SPNode(name="Ana PLC", node_type="component", reliability=0.995),
            SPNode(name="Yedek PLC", node_type="component", reliability=0.995),
        ]
        outlet = SPNode(name="Çıkış Vanası", node_type="component",
                        reliability=0.998)

        root.children = [intake, pump_group, filter_sys, control, outlet]

        self._load_example(proj, self.MODE_SP, "Su Pompalama İstasyonu", """
        <h2 style="color:#1565C0;">Su Pompalama İstasyonu — Seri/Paralel</h2>
        <hr>

        <h3>Sistem Tanımı</h3>
        <p>Bir su pompalama istasyonu 5 ana bloktan oluşur. Bloklar
        <b>seri</b> bağlıdır — su sırayla her bloktan geçmelidir.
        Ancak kritik blokların içinde <b>paralel yedeklilik</b> vardır.</p>

        <h3>Sistem Yapısı</h3>
        <pre style="background:#f5f5f5; padding:10px; border-radius:4px;">
  Giriş Vanası → [Pompa 1 ║ Pompa 2 ║ Pompa 3] → [Kaba F. → İnce F.] → [Ana PLC ║ Yedek PLC] → Çıkış Vanası
    R=0.998       3'lü paralel pompa             Seri filtre             Paralel kontrol          R=0.998
        </pre>

        <h3>Hesaplama Adımları</h3>
        <table cellpadding="5" style="border-collapse:collapse; width:100%;">
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;"><b>Pompa Grubu (paralel)</b></td>
            <td style="border:1px solid #ccc;">
            R = 1 − (1−0.94)³ = 1 − 0.06³ = 1 − 0.000216 = <b>0.999784</b><br>
            3 paralel pompa ile güvenilirlik 0.94'ten 0.9998'e çıktı!</td></tr>
        <tr>
            <td style="border:1px solid #ccc;"><b>Filtreleme (seri)</b></td>
            <td style="border:1px solid #ccc;">
            R = 0.99 × 0.98 = <b>0.9702</b><br>
            Seri bağlı — her ikisi de çalışmalı</td></tr>
        <tr style="background:#E3F2FD;">
            <td style="border:1px solid #ccc;"><b>Kontrol (paralel)</b></td>
            <td style="border:1px solid #ccc;">
            R = 1 − (0.005)² = <b>0.999975</b></td></tr>
        <tr>
            <td style="border:1px solid #ccc;"><b>Tüm Sistem (seri)</b></td>
            <td style="border:1px solid #ccc;">
            R = 0.998 × 0.9998 × 0.9702 × 0.99998 × 0.998 ≈ <b>0.966</b></td></tr>
        </table>

        <h3>Yorum</h3>
        <ul>
        <li>3'lü paralel pompa: tek pompa R=0.94 → grup R=0.9998 (muazzam iyileşme)</li>
        <li>Seri filtre zincirin en zayıf halkası — yedek filtre eklense R artar</li>
        <li>Kontrol PLC yedekli olduğu için neredeyse mükemmel</li>
        </ul>
        """)

    # ── Kullanım Kılavuzu ────────────────────────────────────────

    def _show_guide(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Nasıl Kullanılır? — HÖA Analizörü Kılavuzu")
        dlg.resize(820, 650)
        layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Sans", 10))
        text.setStyleSheet("QTextEdit { background-color: #ffffff; color: #222222; }")
        text.setHtml(self._guide_html())
        layout.addWidget(text)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        btn_example = QPushButton("Örnek Proje Yükle")
        btn_example.clicked.connect(lambda: (dlg.close(),
                                             self._example_fire_safety()))
        btn_bar.addWidget(btn_example)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(dlg.close)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)
        dlg.exec()

    def _show_welcome(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Hoş Geldiniz — HÖA Analizörü")
        dlg.resize(780, 600)
        layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Sans", 10))
        text.setStyleSheet("QTextEdit { background-color: #ffffff; color: #222222; }")
        text.setHtml(self._welcome_html())
        layout.addWidget(text)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        btn_example = QPushButton("Örnek Proje ile Başla")
        btn_example.setStyleSheet(
            "background-color: #1976D2; color: white; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px;")
        btn_example.clicked.connect(lambda: (dlg.close(),
                                             self._example_redundant_pump()))
        btn_bar.addWidget(btn_example)
        btn_empty = QPushButton("Boş Proje ile Başla")
        btn_empty.clicked.connect(dlg.close)
        btn_bar.addWidget(btn_empty)
        layout.addLayout(btn_bar)
        dlg.exec()

    @staticmethod
    def _welcome_html() -> str:
        return """
        <h2 style="color: #1565C0; text-align: center;">
        HÖA Analizörü'ne Hoş Geldiniz</h2>
        <p style="text-align: center; font-size: 13px; color: #555;">
        Hata Ağacı (FTA), Olay Ağacı (ETA) ve Seri/Paralel Sistem Analizi</p>
        <hr>

        <h3 style="color: #E65100;">Bu Uygulama Ne Yapar?</h3>
        <p>Güvenlik ve güvenilirlik mühendisliğinde kullanılan üç temel analiz
        yöntemini tek bir arayüzde sunar:</p>

        <table cellpadding="6" cellspacing="0" style="width: 100%; border-collapse: collapse;">
        <tr style="background: #E3F2FD;">
            <td style="width: 30%; font-weight: bold; border: 1px solid #ccc;">
            Hata Ağacı (FTA)</td>
            <td style="border: 1px solid #ccc;">
            "Sistem neden arızalanır?" sorusuna cevap verir. Tepe olaydan
            başlayarak AND/OR/VOTE kapılarıyla kök nedenlere iner.<br>
            <b>Çıktılar:</b> Tepe olay olasılığı, Minimal Kesim Kümeleri,
            Önem Ölçüleri (FV, RAW, RRW)</td>
        </tr>
        <tr>
            <td style="font-weight: bold; border: 1px solid #ccc;">
            Olay Ağacı (ETA)</td>
            <td style="border: 1px solid #ccc;">
            "Kaza başladıktan sonra ne olur?" sorusuna cevap verir.
            Başlatıcı olaydan ilerleyerek güvenlik bariyerlerinin
            başarı/başarısızlık dallarını izler.<br>
            <b>Çıktılar:</b> 2ⁿ sonuç dizisi, her birinin olasılık ve frekansı</td>
        </tr>
        <tr style="background: #E3F2FD;">
            <td style="font-weight: bold; border: 1px solid #ccc;">
            Seri / Paralel</td>
            <td style="border: 1px solid #ccc;">
            Sistem güvenilirliğini blok diyagram mantığıyla hesaplar.
            Seri bağlı bileşenler zincirin en zayıf halkasıdır;
            paralel bağlı bileşenler yedeklilik sağlar.<br>
            <b>Çıktılar:</b> R<sub>sistem</sub>, F<sub>sistem</sub>,
            bileşen bazlı katkılar</td>
        </tr>
        </table>

        <h3 style="color: #2E7D32;">Hızlı Başlangıç</h3>
        <ol>
        <li><b>Örnekler</b> menüsünden hazır bir proje yükleyin</li>
        <li>Sonuçlar ve diyagram sağ panelde otomatik görünür</li>
        <li>Sol panelden olayları / kapıları düzenleyin — sonuçlar anında güncellenir</li>
        </ol>

        <p style="text-align: center; color: #999; font-size: 11px;">
        Detaylı kılavuz: Yardım → Nasıl Kullanılır?</p>
        """

    @staticmethod
    def _guide_html() -> str:
        return """
        <h2 style="color: #1565C0;">Kullanım Kılavuzu</h2>
        <hr>

        <h3 style="color: #B71C1C;">1. Hata Ağacı Analizi (FTA)</h3>
        <p><b>Amaç:</b> İstenmeyen bir olayın (tepe olay) meydana gelme
        olasılığını ve kök nedenlerini bulmak.</p>

        <p><b>Adım adım:</b></p>
        <ol>
        <li><b>Hata Ağacı</b> moduna geçin (üst çubuk)</li>
        <li><b>Temel olaylar</b> ekleyin (her biri bir bileşen arızası):
            <ul>
            <li><i>Doğrudan:</i> Güvenilirlik R değerini girin (ör: 0.99)</li>
            <li><i>Zamana bağlı:</i> λ (arıza oranı) ve t (süre) girin →
            R = e<sup>−λt</sup></li>
            </ul></li>
        <li><b>Mantık kapıları</b> ekleyin ve alt elemanlarını seçin:
            <ul>
            <li><b>AND:</b> Tüm alt elemanlar arızalanmalı →
            F = F₁ × F₂ × ... × Fₙ</li>
            <li><b>OR:</b> Herhangi biri arızalanması yeterli →
            F = 1 − (1−F₁)(1−F₂)...(1−Fₙ)</li>
            <li><b>VOTE k/n:</b> n elemandan en az k tanesi arızalanmalı</li>
            </ul></li>
        <li><b>Tepe olay</b> olarak bir kapıyı seçin</li>
        <li>Sonuçlar otomatik hesaplanır:
            <ul>
            <li><b>Tepe Olay Olasılığı</b> — F(sistem)</li>
            <li><b>Minimal Kesim Kümeleri (MCS)</b> — Sistemi tek başına
            fail ettiren en küçük bileşen kombinasyonları</li>
            <li><b>Önem Ölçüleri</b> — Hangi bileşen en kritik?
                <ul>
                <li><b>FV (Fussell-Vesely):</b> Bileşenin toplam riske katkı oranı</li>
                <li><b>RAW:</b> Bileşen arızalanırsa risk kaç kat artar</li>
                <li><b>RRW:</b> Bileşen mükemmel olursa risk kaç kat azalır</li>
                </ul></li>
            </ul></li>
        </ol>

        <h3 style="color: #E65100;">2. Olay Ağacı Analizi (ETA)</h3>
        <p><b>Amaç:</b> Bir başlatıcı olaydan sonra olası kaza senaryolarını
        ve frekanslarını belirlemek.</p>

        <p><b>Adım adım:</b></p>
        <ol>
        <li><b>Olay Ağacı</b> moduna geçin</li>
        <li><b>Başlatıcı olay</b> adı ve frekansını girin (ör: LOCA, f = 10⁻⁴/yıl)</li>
        <li><b>Dallar</b> ekleyin — her biri bir güvenlik bariyeri:
            <ul>
            <li>Başarı olasılığı P(S) girin (ör: 0.99)</li>
            <li>Başarısızlık = 1 − P(S)</li>
            </ul></li>
        <li>N dal için 2ᴺ sonuç dizisi otomatik hesaplanır</li>
        <li>Her sonucun olasılığı = dallar boyunca P'lerin çarpımı</li>
        <li>Frekans = Başlatıcı olay frekansı × Sonuç olasılığı</li>
        <li>Sonuç tablolarına etiket yazabilirsiniz (ör: "Güvenli Duruş")</li>
        </ol>

        <h3 style="color: #1565C0;">3. Seri / Paralel Sistem</h3>
        <p><b>Amaç:</b> Sistem güvenilirliğini bileşen düzenine göre hesaplamak.</p>

        <p><b>Formüller:</b></p>
        <table cellpadding="4" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background: #E3F2FD;">
            <td style="border: 1px solid #ccc; font-weight: bold;">Seri</td>
            <td style="border: 1px solid #ccc;">
            R<sub>sis</sub> = R₁ × R₂ × ... × Rₙ<br>
            <i>Bir bileşen bozulursa sistem durur</i></td>
        </tr>
        <tr>
            <td style="border: 1px solid #ccc; font-weight: bold;">Paralel</td>
            <td style="border: 1px solid #ccc;">
            R<sub>sis</sub> = 1 − (1−R₁)(1−R₂)...(1−Rₙ)<br>
            <i>Tüm bileşenler bozulursa sistem durur (yedeklilik)</i></td>
        </tr>
        </table>

        <p><b>Adım adım:</b></p>
        <ol>
        <li><b>Seri/Paralel</b> moduna geçin</li>
        <li>Kök düğüm tipi Seri veya Paralel olarak ayarlanır</li>
        <li><b>Bileşen Ekle</b> ile bileşenler ekleyin (ad + R değeri)</li>
        <li><b>Grup Ekle</b> ile iç içe seri/paralel gruplar oluşturun</li>
        <li>Sistem güvenilirliği otomatik hesaplanır</li>
        </ol>

        <h3 style="color: #2E7D32;">Genel İpuçları</h3>
        <ul>
        <li>Her değişiklik sonuçları <b>otomatik günceller</b> — hesapla butonuna gerek yok</li>
        <li><b>Örnekler</b> menüsünden hazır projeler yükleyerek deneyin</li>
        <li><b>Dosya → PDF Rapor</b> ile tüm sonuçları dışa aktarın</li>
        <li><b>Büyüt</b> butonuyla diyagramı tam ekran görün</li>
        <li>Projeler JSON formatında kaydedilir — istediğiniz zaman açabilirsiniz</li>
        </ul>
        """

    def _show_about(self):
        QMessageBox.about(
            self, "HÖA Analizörü Hakkında",
            "<h3>Hata Ağacı & Olay Ağacı Analizörü</h3>"
            "<p>Sürüm 3.0</p>"
            "<p>Hata ağaçları, olay ağaçları ve seri/paralel sistemleri "
            "oluşturmak, analiz etmek ve görselleştirmek için "
            "masaüstü uygulaması.</p>"
            "<p><b>Özellikler:</b></p>"
            "<ul>"
            "<li>AND / OR / VOTE(k/n) kapı mantığı</li>"
            "<li>Minimal Kesim Kümeleri (MCS)</li>"
            "<li>Önem Ölçüleri (Birnbaum, FV, RAW, RRW)</li>"
            "<li>Olay ağacı: sıralı dal analizi</li>"
            "<li>Seri/Paralel sistem güvenilirlik hesaplayıcı</li>"
            "<li>Otomatik hesaplama ve Graphviz diyagramları</li>"
            "<li>PDF rapor çıktısı</li>"
            "<li>Hazır örnek projeler</li>"
            "</ul>"
            "<p>PyQt6 + Graphviz + fpdf2 ile geliştirilmiştir</p>")


def _check_graphviz() -> bool:
    import shutil
    import subprocess
    if shutil.which("dot") is None:
        return False
    try:
        subprocess.run(["dot", "-V"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("HÖA Analizörü")
    window = MainWindow()
    window.show()

    if not _check_graphviz():
        import platform
        if platform.system() == "Windows":
            install_msg = ("Kurmak için:\n"
                           "  https://graphviz.org/download/\n"
                           "  adresinden Graphviz'i indirip kurun.\n\n"
                           "Kurulu ise DLL dosyaları eksik olabilir.")
        else:
            install_msg = ("Kurmak için:\n"
                           "  sudo apt install graphviz")
        QMessageBox.warning(
            window, "Graphviz Çalışmıyor",
            "Graphviz (dot) çalıştırılamıyor.\n"
            "Diyagramlar oluşturulamayacak.\n\n"
            f"{install_msg}\n\n"
            "Hesaplama ve sonuçlar yine de çalışacaktır.")

    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        window._load_file(sys.argv[1])
    else:
        QTimer.singleShot(200, window._show_welcome)

    sys.exit(app.exec())
