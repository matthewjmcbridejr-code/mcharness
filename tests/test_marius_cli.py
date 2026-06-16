import pytest
from scripts.marius_chat import parse_command, ApiClient, MariusCLI
from unittest.mock import MagicMock, patch

def test_parse_command_chat():
    cmd, args = parse_command("Hello Marius")
    assert cmd is None
    assert args == ["Hello Marius"]

def test_parse_command_simple():
    cmd, args = parse_command("/status")
    assert cmd == "status"
    assert args == [""]

def test_parse_command_remember_plain():
    cmd, args = parse_command("/remember This is a note")
    assert cmd == "remember"
    assert args == ["general", "This is a note"]

def test_parse_command_remember_category():
    cmd, args = parse_command("/remember project: Finish the CLI")
    assert cmd == "remember"
    assert args == ["project", "Finish the CLI"]

def test_parse_command_recall():
    cmd, args = parse_command("/recall project")
    assert cmd == "recall"
    assert args == ["project"]

def test_parse_command_handoff():
    cmd, args = parse_command("/handoff codex Finish the implementation")
    assert cmd == "handoff"
    assert args == ["codex", "Finish the implementation"]

@patch("requests.post")
def test_api_client_chat(mock_post):
    mock_post.return_value.json.return_value = {"response": "Hi", "provider": "test"}
    mock_post.return_value.status_code = 200
    
    client = ApiClient("http://localhost:8126")
    res = client.get_chat("Hello")
    assert res == {"response": "Hi", "provider": "test"}
    mock_post.assert_called_once()

@patch("requests.get")
def test_api_client_offline(mock_get):
    import requests
    mock_get.side_effect = requests.exceptions.ConnectionError()
    
    client = ApiClient("http://localhost:8126")
    res = client.get_status()
    assert res is None

def test_cli_once_mode():
    with patch("scripts.marius_chat.ApiClient.get_chat") as mock_chat:
        mock_chat.return_value = {"response": "I am Marius", "provider": "mock"}
        cli = MariusCLI("http://localhost:8126")
        
        # Test --once behavior via run_command
        cli.run_command("Who are you?")
        mock_chat.assert_called_once_with("Who are you?")
