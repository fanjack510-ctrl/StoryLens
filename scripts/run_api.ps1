$ErrorActionPreference = "Stop"
# StoryLens does not use WebSocket; --ws none avoids optional websockets import failures.
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload --ws none
