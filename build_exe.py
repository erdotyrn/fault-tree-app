#!/usr/bin/env python3
"""
HÖA Analizörü — Taşınabilir .exe / binary oluşturucu

Kullanım:
    python build_exe.py

Linux'ta Linux binary, Windows'ta .exe üretir.
Graphviz sistem binary'lerini de paketin içine dahil eder.
"""

import os
import sys
import shutil
import platform
import subprocess

APP_NAME = "HÖA Analizörü"
ENTRY = "main.py"
ICON = None  # İsteğe bağlı: "icon.ico" dosyası eklenebilir

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")


def find_graphviz_binaries():
    """Graphviz binary'lerini bul ve listeye ekle."""
    bins = ["dot", "neato", "fdp", "sfdp", "twopi", "circo"]
    if platform.system() == "Windows":
        bins = [b + ".exe" for b in bins]

    found = []
    for b in bins:
        path = shutil.which(b)
        if path:
            found.append(path)

    if not found:
        print("UYARI: Graphviz bulunamadı! Diyagram oluşturma çalışmayacak.")
        print("       Lütfen Graphviz'i yükleyin:")
        if platform.system() == "Windows":
            print("       https://graphviz.org/download/")
        else:
            print("       sudo apt install graphviz")
    return found


def build():
    os.chdir(BASE_DIR)

    graphviz_bins = find_graphviz_binaries()

    add_data = []
    for f in ["nuklear_ornek.json", "sample_project.json"]:
        if os.path.exists(f):
            sep = ";" if platform.system() == "Windows" else ":"
            add_data.append(f"--add-data={f}{sep}.")

    add_binary = []
    gv_dest = "graphviz_bin"
    for gv in graphviz_bins:
        sep = ";" if platform.system() == "Windows" else ":"
        add_binary.append(f"--add-binary={gv}{sep}{gv_dest}")

    # Graphviz config ve kütüphaneleri
    if platform.system() != "Windows":
        gv_lib_dirs = [
            "/usr/lib/x86_64-linux-gnu/graphviz",
            "/usr/lib/graphviz",
            "/usr/lib64/graphviz",
        ]
        for d in gv_lib_dirs:
            if os.path.isdir(d):
                sep = ":"
                add_binary.append(f"--add-binary={d}/*{sep}graphviz_lib")
                break
    else:
        dot_path = shutil.which("dot.exe")
        if dot_path:
            gv_dir = os.path.dirname(dot_path)
            config_files = [
                f for f in os.listdir(gv_dir)
                if f.endswith(".dll") or f.startswith("config")
            ]
            for cf in config_files:
                full = os.path.join(gv_dir, cf)
                add_binary.append(f"--add-binary={full};{gv_dest}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        f"--name={APP_NAME}",
        "--windowed",
        "--hidden-import=PyQt6.sip",
        "--collect-submodules=graphviz",
    ]

    if ICON and os.path.exists(ICON):
        cmd.append(f"--icon={ICON}")

    cmd.extend(add_data)
    cmd.extend(add_binary)
    cmd.append(ENTRY)

    print("=" * 60)
    print(f"  {APP_NAME} — Build başlıyor")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Graphviz binary: {len(graphviz_bins)} adet bulundu")
    print("=" * 60)
    print()
    print("Komut:", " ".join(cmd))
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nHATA: Build başarısız oldu!")
        sys.exit(1)

    output_dir = os.path.join(DIST_DIR, APP_NAME)
    print()
    print("=" * 60)
    print(f"  BUILD BAŞARILI!")
    print(f"  Çıktı: {output_dir}")
    print()
    if platform.system() == "Windows":
        print(f"  Çalıştır: {output_dir}\\{APP_NAME}.exe")
    else:
        print(f"  Çalıştır: {output_dir}/{APP_NAME}")
    print()
    print("  Bu klasörü USB'ye kopyalayabilirsiniz.")
    print("=" * 60)


if __name__ == "__main__":
    build()
