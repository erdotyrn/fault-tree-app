#!/usr/bin/env python3
"""Programatik olarak 3 örnek projeyi yükleyip ekran görüntüsü alır."""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from app import MainWindow

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1400, 850)
    window.show()

    steps = []

    def take_screenshot(name):
        def _do():
            path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
            pixmap = window.grab()
            pixmap.save(path, "PNG")
            print(f"Screenshot: {path}")
        return _do

    def load_ft():
        window._example_redundant_pump()

    def load_et():
        window._example_loca_et()

    def load_sp():
        window._example_power_supply_sp()

    def finish():
        app.quit()

    schedule = [
        (500, load_ft),
        (1500, take_screenshot("01_hata_agaci")),
        (2000, load_et),
        (3000, take_screenshot("02_olay_agaci")),
        (3500, load_sp),
        (4500, take_screenshot("03_seri_paralel")),
        (5000, finish),
    ]

    for delay, func in schedule:
        QTimer.singleShot(delay, func)

    app.exec()


if __name__ == "__main__":
    main()
