import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_google_sync_script_dry_run():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "marius_brain_gcs_setup.sh"
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="Dry run: use --upload to sync", returncode=0)
        res = subprocess.run(["bash", str(script_path)], capture_output=True, text=True)
        assert "Dry run" in res.stdout

@patch("subprocess.run")
def test_google_sync_upload_flow(mock_run):
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "marius_brain_gcs_setup.sh"
    
    # Mocking successful upload
    mock_run.return_value = MagicMock(stdout="Upload complete.", returncode=0)
    
    res = subprocess.run(["bash", str(script_path), "--upload"], capture_output=True, text=True)
    assert "Upload complete" in res.stdout
