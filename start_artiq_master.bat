@echo off
title ARTIQ Master
call C:\ProgramData\Anaconda3\Scripts\activate.bat C:\ProgramData\Anaconda3
call activate artiq
cd C:\Repos\artiq-master
python C:\Repos\artiq\artiq\frontend\artiq_master.py --repository C:\Repos\artiq-work
