@echo off
setlocal

set MODE=%1

if /i "%MODE%"=="test" goto TEST_MODE

REM ══════════════════════════════════════════════
REM  NORMAL MOD: C++ derle (SFML 2.6.2) ve calistir
REM ══════════════════════════════════════════════
echo [BUILD] SFML 2.6.2 ile derleme baslatiliyor...
set PATH=C:\msys64\mingw64\bin;%PATH%

set SFML_DIR=%~dp0SFML-2.6.2

g++ main.cpp PIDController.cpp -o sim.exe ^
-I"%SFML_DIR%\include" ^
-L"%SFML_DIR%\lib" ^
-lsfml-graphics -lsfml-window -lsfml-system -lsfml-network ^
-lws2_32

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Derleme basarisiz!
    echo        Python mock test icin: .\baslat.bat test
    pause
    exit /b 1
)

echo [SUCCESS] Derleme basarili!
echo.

REM SFML 2.x DLL'leri exe'nin yanına kopyala (ilk seferde)
if not exist sfml-graphics-2.dll (
    echo [SETUP] SFML DLL dosyalari kopyalaniyor...
    copy "%SFML_DIR%\bin\*.dll" . >nul 2>&1
    echo [SETUP] Tamam.
)

echo [BRAIN] Python sunucusu yeni pencerede baslatiliyor...
start "Python Brain" cmd /k "C:\Users\Ali\anaconda3\python.exe brain.py"

echo [SIM] YOLOv8 modeli yuklenirken bekleniyor (8 saniye)...
timeout /t 8 /nobreak >nul

echo [SIM] Simulasyon baslatiliyor...
sim.exe
goto END

REM ══════════════════════════════════════════════
REM  TEST MODU: Sadece Python (C++ olmadan)
REM ══════════════════════════════════════════════
:TEST_MODE
echo ╔══════════════════════════════════════════╗
echo ║   TEST MODU  (C++ gerekmez)              ║
echo ║   brain.py + Python mock sender          ║
echo ╚══════════════════════════════════════════╝
echo.

echo [BRAIN] Python sunucusu yeni pencerede baslatiliyor...
start "Python Brain" cmd /k "python brain.py"

echo [MOCK] 2 saniye bekleniyor, sunucu hazirlansin...
timeout /t 2 /nobreak >nul

echo [MOCK] Sahte C++ goruntuler gonderiliyor...
echo        (Durdurmak icin Ctrl+C)
echo.
python test_sender.py

:END
endlocal