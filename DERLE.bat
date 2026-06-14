@echo off
chcp 65001 >nul
title HOA Analizoru - Windows Derleyici
echo ============================================================
echo   HOA Analizoru - Windows .exe Derleyici (v3)
echo ============================================================
echo.

REM --- Python var mi? ---
where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi. Once https://python.org adresinden
    echo       Python 3.10+ kurun ve "Add to PATH" secenegini isaretleyin.
    pause
    exit /b 1
)

REM --- Graphviz (dot.exe) var mi? Derleme sirasinda paketlenecek ---
where dot >nul 2>nul
if errorlevel 1 (
    echo UYARI: Graphviz "dot" PATH'te bulunamadi.
    echo        https://graphviz.org/download/ adresinden Graphviz kurun
    echo        ve kurulum sirasinda "Add to PATH" secin. Aksi halde
    echo        diyagram motoru exe icine paketlenemez.
    echo.
    pause
)

echo [1/3] Gerekli paketler kuruluyor...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo HATA: Paket kurulumu basarisiz.
    pause
    exit /b 1
)

echo.
echo [2/3] Uygulama derleniyor (PyInstaller)...
python build_exe.py
if errorlevel 1 (
    echo HATA: Derleme basarisiz.
    pause
    exit /b 1
)

echo.
echo [3/3] Tamamlandi!
echo   Cikti klasoru: dist\HOA Analizoru
echo   Calistir:      dist\HOA Analizoru\HOA Analizoru.exe
echo   Bu klasoru USB'ye kopyalayip baska bilgisayarda da calistirabilirsiniz.
echo ============================================================
pause
