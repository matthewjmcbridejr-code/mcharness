# Marius-Brain: Google Agent Search Foundation

Marius-Brain is the giant searchable memory layer for Marius, Warden, and GradeMy. It uses Google Agent Search (Vertex AI Search / Discovery Engine) as the backend for large-scale document and project-context recall.

## Architecture
- **Local-first**: Local JSONL-based keyword search is always available and used as a fallback.
- **Giant Memory**: Google Agent Search provides semantic and large-scale search when local memory is insufficient.
- **Safety**: Strict exclusion rules ensure that secrets, keys, and tokens are never exported or uploaded.

## Prerequisites
- Google Cloud CLI installed.
- Active Google Cloud project with billing enabled.
- Application Default Credentials (ADC) configured.

## Setup Steps

### 1. Verification
Run the doctor script to check your local and cloud state:
```bash
bash scripts/google_agent_search_doctor.sh
```

### 2. Authentication
If ADC is missing, run:
```bash
gcloud auth application-default login --no-launch-browser
```

### 3. Local Export
Generate a safe JSONL export of your project context:
```text
/search export warden
```
This generates a file in `~/.local/share/marius/brain/exports/warden.jsonl`.

### 4. Cloud Foundation (Optional)
Setup GCS bucket and upload exports:
```bash
bash scripts/marius_brain_gcs_setup.sh
```

## Secret Exclusion Policy
The following are NEVER indexed:
- `.env` files
- Private keys (`.pem`, `.key`, `id_rsa`)
- Files containing strings like `API_KEY`, `SECRET`, `TOKEN`.
- Folders like `.git`, `.venv`, `node_modules`.

## Provider Configuration
Configure the active search provider via environment variables:
- `MARIUS_SEARCH_PROVIDER=local|google`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_AGENT_SEARCH_ENGINE_ID`

## Troubleshooting
- **Permission Denied**: Ensure your account has `Discovery Engine Admin` and `Storage Admin` roles.
- **Billing Issue**: Verify billing is linked via `gcloud billing projects describe PROJECT_ID`.
- **Search Error**: Check `GOOGLE_AGENT_SEARCH_ENGINE_ID` matches your Discovery Engine setup in the console.
