#!/usr/bin/env bash
# Deploy SLINGSHOT to Cloud Run. The API key is injected from Secret Manager at
# runtime (--set-secrets) — never baked into the image or committed.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-deepmind-hack26blr-4182}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE="slingshot"

echo "Deploying $SERVICE to project $PROJECT ($REGION)…"

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --quiet \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 3600 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=0,DEMO_AGENT_MODEL=gemini-3.1-flash-live-preview,NASA_API_KEY=DEMO_KEY,SLINGSHOT_MEDIA=1,LOG_LEVEL=INFO" \
  --set-secrets "GOOGLE_API_KEY=gemini-api-key:latest"

echo "Done. Open the printed service URL. (Temp account — export everything before it's deleted.)"
