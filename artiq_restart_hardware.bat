@echo off
title Restart ARTIQ
call C:\ProgramData\Anaconda3\Scripts\activate.bat C:\ProgramData\Anaconda3
call activate artiq
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\labrad;%USERPROFILE%\artiq;%USERPROFILE%\artiq\artiq;%USERPROFILE%\artiq\artiq\.pulse_sequence;%USERPROFILE%\artiq-work;%USERPROFILE%\artiq-master
pushd %USERPROFILE%\artiq-master
python %USERPROFILE%\artiq\artiq\frontend\artiq_flash.py start & popd