@echo off
chcp 65001 >nul
rem 打包成单文件 exe：dist\透明模板制作.exe
rem 注意：本文件必须是 UTF-8 编码，chcp 65001 让 cmd 按 UTF-8 解析 --name 里的中文
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --collect-all customtkinter ^
    --add-data "icon.ico;." --icon=icon.ico ^
    --name 透明模板制作 main.py
if errorlevel 1 pause
