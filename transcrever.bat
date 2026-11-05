@echo off
call "%~dp0venv\Scripts\activate.bat"
python "%~dp0transcrever.py" %1
pause
