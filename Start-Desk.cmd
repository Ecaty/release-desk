@echo off
rem Starts Release Desk. Optional argument: the Unity project folder.
cd /d "%~dp0"
python -m desk.server %*
