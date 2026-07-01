@echo off
setlocal

set PRG=%~dp0%~nx0

:findLoop
if exist "%PRG%" goto found
exit /b 1

:found
"%~dp0\.mvn\wrapper\mvnw" %*
