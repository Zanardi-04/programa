@echo off
chcp 65001 >nul
title Criar executavel - Consulta de Enderecos
cd /d "%~dp0"
echo ==============================================
echo Criador do executavel - Consulta de Enderecos
echo ==============================================
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo ERRO: Python nao foi encontrado.
  echo Instale Python 3.11 ou superior em https://www.python.org/downloads/windows/
  echo Marque "Add Python to PATH" durante a instalacao.
  pause
  exit /b 1
)
py -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo ERRO: instale Python 3.11 ou superior.
  pause
  exit /b 1
)
py -m pip install --upgrade pip
if errorlevel 1 goto erro
py -m pip install pyinstaller
if errorlevel 1 goto erro
py -m PyInstaller --noconfirm --clean --onedir --windowed --icon=logo_mapa_documento.ico --name ConsultaEnderecos consulta_enderecos.py
if errorlevel 1 goto erro
copy /Y lista_ruas_original.txt dist\ConsultaEnderecos\ >nul
if errorlevel 1 goto erro
copy /Y oficiais.json dist\ConsultaEnderecos\ >nul
if errorlevel 1 goto erro
copy /Y logo_mapa_documento.png dist\ConsultaEnderecos\ >nul
if errorlevel 1 goto erro
copy /Y logo_mapa_documento.ico dist\ConsultaEnderecos\ >nul
if errorlevel 1 goto erro
xcopy /E /I /Y recursos dist\ConsultaEnderecos\recursos >nul
if errorlevel 1 goto erro
echo.
echo EXE criado com sucesso em:
echo %CD%\dist\ConsultaEnderecos\ConsultaEnderecos.exe
echo Mantenha os arquivos de dados na mesma pasta do EXE.
pause
exit /b 0
:erro
echo.
echo ERRO: nao foi possivel concluir a compilacao. Confira a mensagem acima.
pause
exit /b 1
