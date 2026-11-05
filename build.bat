@echo off
setlocal
cd /d "%~dp0"

echo Instalando dependencias...
"%~dp0venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto erro

echo Gerando o executavel...
"%~dp0venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean transcritor.spec
if errorlevel 1 goto erro

echo.
echo Pronto: %~dp0dist\Transcritor\Transcritor.exe
pause
exit /b 0

:erro
echo.
echo ERRO: o build falhou. Veja as mensagens acima.
pause
exit /b 1
