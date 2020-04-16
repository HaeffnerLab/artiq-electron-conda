@echo off
title ARTIQ Master
if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat" call "%USERPROFILE%\Anaconda3\Scripts\activate.bat" "%USERPROFILE%\Anaconda3"
if exist "%PROGRAMDATA%\Anaconda3\Scripts\activate.bat" call "%PROGRAMDATA%\Anaconda3\Scripts\activate.bat" "%PROGRAMDATA%\Anaconda3"
call activate artiq
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\labrad;%USERPROFILE%\artiq;%USERPROFILE%\artiq\artiq;%USERPROFILE%\artiq\artiq\.pulse_sequence;%USERPROFILE%\artiq-work;%USERPROFILE%\artiq-master
pushd %USERPROFILE%\artiq-master
python %USERPROFILE%\artiq\artiq\frontend\artiq_master.py --repository %USERPROFILE%\artiq-work & popd