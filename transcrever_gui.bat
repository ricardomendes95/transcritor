@echo off
call "%~dp0venv\Scripts\activate.bat"
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0transcrever_gui.py"
