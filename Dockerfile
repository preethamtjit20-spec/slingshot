# SLINGSHOT — container for Cloud Run.
# The GOOGLE_API_KEY is NOT baked in; Cloud Run injects it from Secret Manager at
# runtime via --set-secrets (see deploy.sh). Nothing secret lives in this image.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# The app expects to run from the app/ directory (static/ + slingshot_mission are relative).
WORKDIR /app/app
ENV PORT=8080 PYTHONUNBUFFERED=1
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
