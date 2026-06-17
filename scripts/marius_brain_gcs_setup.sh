#!/bin/bash
# scripts/marius_brain_gcs_setup.sh
# Marius Google Cloud Storage setup for searchable memory

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GCLOUD_PATH="${REPO_ROOT}/google-cloud-sdk/path.bash.inc"

if [ -f "${GCLOUD_PATH}" ]; then
    source "${GCLOUD_PATH}"
fi

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "${PROJECT_ID}" ]; then
    echo "ERROR: No active Google Cloud project. Run 'gcloud config set project <PROJECT_ID>'"
    exit 1
fi

BUCKET_NAME="marius-brain-${PROJECT_ID}"
LOCATION="us-central1"

echo "== Marius Brain GCS Setup =="
echo "Project: ${PROJECT_ID}"
echo "Bucket:  gs://${BUCKET_NAME}"
echo "Region:  ${LOCATION}"

if gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "Bucket already exists."
else
    echo "Creating bucket..."
    gcloud storage buckets create "gs://${BUCKET_NAME}" --location="${LOCATION}" --uniform-bucket-level-access
    echo "Bucket created."
fi

EXPORTS_DIR="${HOME}/.local/share/marius/brain/exports"
if [ -d "${EXPORTS_DIR}" ]; then
    echo "Uploading exports..."
    gcloud storage cp "${EXPORTS_DIR}"/*.jsonl "gs://${BUCKET_NAME}/exports/"
    echo "Upload complete."
else
    echo "No local exports found to upload."
    echo "Run '/search export warden' in marius chat first."
fi

echo "Done."
