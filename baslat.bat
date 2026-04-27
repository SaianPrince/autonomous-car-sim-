@echo off
echo [BUILD] Derleme baslatiliyor...
set PATH=C:\msys64\mingw64\bin;%PATH%

g++ main.cpp -o sim.exe -lsfml-graphics -lsfml-window -lsfml-system -lsfml-network -lws2_32

if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Derleme basarili! Simülasyon baslatiliyor...
    sim.exe
) else (
    echo [ERROR] Derleme sirasinda hata olustu.
    pause
)
