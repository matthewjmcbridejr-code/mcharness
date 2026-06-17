import pytest
from unittest.mock import MagicMock, patch
from src.marius.google_search_provider import GoogleAgentSearchProvider

@patch("src.marius.google_search_provider.os.getenv")
def test_google_provider_status(mock_getenv):
    mock_getenv.side_effect = lambda k, default=None: {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_AGENT_SEARCH_ENGINE_ID": "test-engine"
    }.get(k, default)
    
    with patch("google.cloud.discoveryengine_v1.SearchServiceClient") as mock_client:
        provider = GoogleAgentSearchProvider()
        status = provider.status()
        assert status["provider"] == "google"
        assert status["project_id"] == "test-project"
        assert status["engine_id"] == "test-engine"
        assert status["client_installed"] is True

@patch("src.marius.google_search_provider.os.getenv")
def test_google_provider_search_mock(mock_getenv):
    mock_getenv.side_effect = lambda k, default=None: {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_AGENT_SEARCH_ENGINE_ID": "test-engine"
    }.get(k, default)
    
    with patch("google.cloud.discoveryengine_v1.SearchServiceClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.serving_config_path.return_value = "projects/test/locations/global/collections/default_collection/engines/test/servingConfigs/default"
        
        # Mock search response
        mock_result = MagicMock()
        mock_result.document.id = "doc1"
        mock_result.document.name = "projects/test-project/.../documents/doc1"
        mock_result.document.derived_struct_data = {
            "title": "Test Doc",
            "link": "gs://bucket/test.md",
            "snippets": [{"snippet": "Test snippet contents"}]
        }
        
        # Mock pager - it's an iterable of SearchResponse.SearchResult
        mock_client.search.return_value = [mock_result]
        
        provider = GoogleAgentSearchProvider()
        results = provider.search("test query")
        
        assert len(results) == 1
        assert results[0]["title"] == "Test Doc"
        assert results[0]["snippet"] == "Test snippet contents"
        assert results[0]["project"] == "google-brain"

def test_google_provider_fallback_when_unconfigured():
    with patch("src.marius.google_search_provider.os.getenv", return_value=None):
        provider = GoogleAgentSearchProvider()
        # Should fallback to local search
        with patch("src.marius.search_provider.LocalJsonlSearchProvider.search") as mock_local_search:
            mock_local_search.return_value = [{"title": "Local Result"}]
            results = provider.search("query")
            assert results[0]["title"] == "Local Result"
