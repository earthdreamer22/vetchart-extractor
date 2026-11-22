@echo off
rem VetChart Extractor - build a single exe (needs: pip install -r requirements.txt pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --onefile --console --name VetChart_Extractor --hidden-import firebirdsql --hidden-import pymysql --hidden-import psycopg2 --hidden-import pyodbc run.py
