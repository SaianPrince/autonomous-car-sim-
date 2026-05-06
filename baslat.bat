@echo off
setlocal

set MODE=%1

if /i "%MODE%"=="test" goto TEST_MODE

REM ══════════════════════════════════════════════
REM  NORMAL MOD: C++ derle ve calistir
REM ══════════════════════════════════════════════
echo [BUILD] Derleme baslatiliyor...
set PATH=C:\msys64\mingw64\bin;%PATH%

g++ main.cpp -o sim.exe ^
-IC:\msys64\mingw64\include ^
-LC:\msys64\mingw64\lib ^
-lsfml-graphics -lsfml-window -lsfml-system -lsfml-network -lws2_32

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Derleme basarisiz!
    echo        C++ tarafini test etmek icin: .\baslat.bat test
    pause
    exit /b 1
)

echo [SUCCESS] Derleme basarili!
echo.
echo [BRAIN] Python sunucusu yeni pencerede baslatiliyor...
start "Python Brain" cmd /k "python brain.py"

echo [SIM] 2 saniye bekleniyor...
timeout /t 2 /nobreak >nul

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