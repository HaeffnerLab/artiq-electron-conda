@echo off
title ARTIQ Core Analyzer
call C:\ProgramData\Anaconda3\Scripts\activate.bat C:\ProgramData\Anaconda3
call activate artiq
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\labrad;%USERPROFILE%\artiq;%USERPROFILE%\artiq\artiq;%USERPROFILE%\artiq\artiq\.pulse_sequence;%USERPROFILE%\artiq-work;%USERPROFILE%\artiq-master
pushd %USERPROFILE%\artiq-master
For /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c%%a%%b)
For /f "tokens=1-3 delims=/:. " %%a in ("%TIME%") do (if %%a LSS 10 (set mytime=0%%a%%b%%c) else (set mytime=%%a%%b%%c))
if not exist "%USERPROFILE%\artiq-rtio-output\" mkdir %USERPROFILE%\artiq-rtio-output
python %USERPROFILE%\artiq\artiq\frontend\artiq_coreanalyzer.py -w "%USERPROFILE%\artiq-rtio-output\rtio_%mydate%_%mytime%.vcd" %* & popd