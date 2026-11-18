@echo off
rem Entry point for Windows Task Scheduler (task name: NorthwindDQ).
rem A scheduled task does not get your interactive shell's setup, so this file
rem sets everything explicitly: the working directory, the Python path, and a
rem label so each log entry says who started it.
rem
rem Structured results go to logs\dq_check.log (written by dq_check.py).
rem Raw stdout/stderr also go to logs\dq_scheduler_stdout.log, so even a crash
rem before dq_check.py can log (e.g. Python missing) leaves a trace.

set DQ_INVOKED_BY=task-scheduler
cd /d "%~dp0.."
echo ===== %DATE% %TIME% ===== >> logs\dq_scheduler_stdout.log
"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe" scripts\dq_check.py >> logs\dq_scheduler_stdout.log 2>&1
set RC=%ERRORLEVEL%
echo exit code %RC% >> logs\dq_scheduler_stdout.log
exit /b %RC%
