@ECHO OFF

REM Set virtual environment directory (replace with your desired path)
SET "VENV_DIR=%cd%/venv"

REM Check if virtual environment exists
IF EXIST "%VENV_DIR%\Scripts\activate.bat" (
  ECHO Virtual environment found at: %VENV_DIR%
  venv\Scripts\activate.bat
  2nd.bat
) ELSE (
  ECHO Virtual environment not found. Creating new one...
  python -m venv "%VENV_DIR%"
  IF ERRORLEVEL 1 (
    ECHO Error: Failed to create virtual environment.
    EXIT /B 1
  )
  ECHO Virtual environment created successfully.
)
