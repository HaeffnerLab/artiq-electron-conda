@echo off
title ARTIQ Dashboard
call C:\ProgramData\Anaconda3\Scripts\activate.bat C:\ProgramData\Anaconda3
call activate artiq
cd C:\Repos\artiq-work
python C:\Repos\artiq\artiq\frontend\artiq_dashboard.py