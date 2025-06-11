REM **Always check for requirements.txt**
IF EXIST "requirements.txt" (
  ECHO Installing requirements from requirements.txt...
  pip install -r requirements.txt
  IF ERRORLEVEL 1 (
    ECHO Error: Failed to install requirements.
    EXIT /B 1
  )
  ECHO Installation successful.
) ELSE (
  ECHO Warning: requirements.txt not found. Skipping installation.
)

REM Start Django development server (replace 'yourproject' with your project name)
python manage.py makemigrations
python manage.py migrate
START "" python manage.py runserver 0.0.0.0:80
START "" celery --app vividmind beat --loglevel=INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
START "" celery --app=vividmind worker --pool=eventlet --loglevel=INFO
START "" ngrok http 80

cd Redis
redis-server.exe