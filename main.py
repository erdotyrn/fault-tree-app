#!/usr/bin/env python3
"""
FT/ET Analyzer — Fault Tree & Event Tree Analysis Application

Entry point. Launches the PyQt6 GUI.

System requirements:
  - Python 3.10+
  - pip install PyQt6 graphviz
  - sudo apt install graphviz   (system package for diagram rendering)
"""

from app import run

if __name__ == "__main__":
    run()
