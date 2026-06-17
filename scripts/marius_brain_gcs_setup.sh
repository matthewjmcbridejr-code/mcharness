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

if [[ "$*" == *"--upload"* ]]; then
    echo "Rebuilding safe brain exports..."
    "${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/rebuild_brain_exports.py"
fi

if gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "Bucket already exists."
else
    echo "Creating bucket..."
    gcloud storage buckets create "gs://${BUCKET_NAME}" --location="${LOCATION}" --uniform-bucket-level-access
    echo "Bucket created."
fi

EXPORTS_DIR="${HOME}/.local/share/marius/brain/exports"
if [ -d "${EXPORTS_DIR}" ]; then
    if [[ "$*" == *"--upload"* ]]; then
        echo "Uploading exports to gs://${BUCKET_NAME}/brain/exports/ ..."
        gcloud storage cp "${EXPORTS_DIR}"/*.jsonl "gs://${BUCKET_NAME}/brain/exports/"
        echo "Upload complete."
    else
        echo "Dry run: use --upload to sync local brain to GCS."
    fi
else
    echo "No local exports found."
fi

echo "Done."
