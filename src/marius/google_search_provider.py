import os
from typing import List, Dict, Optional, Any
from .search_provider import SearchProvider, LocalJsonlSearchProvider

class GoogleAgentSearchProvider(SearchProvider):
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_AGENT_SEARCH_LOCATION", "global")
        self.engine_id = os.getenv("GOOGLE_AGENT_SEARCH_ENGINE_ID")
        self.data_store_id = os.getenv("GOOGLE_AGENT_SEARCH_DATA_STORE_ID")
        
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from google.cloud import discoveryengine
            self.client = discoveryengine.SearchServiceClient()
        except ImportError:
            self.client = None

    def status(self) -> Dict[str, Any]:
        return {
            "provider": "google",
            "project_id": self.project_id,
            "location": self.location,
            "engine_id": self.engine_id,
            "data_store_id": self.data_store_id,
            "client_installed": self.client is not None,
            "ready": all([self.project_id, self.engine_id, self.client])
        }

    def export(self, project: str, repo_path: str) -> Dict[str, Any]:
        # For now, Google export is just local export followed by a note that GCS upload is manual or via setup script
        local = LocalJsonlSearchProvider()
        res = local.export(project, repo_path)
        res["google_note"] = "Local JSONL generated. Use scripts/marius_brain_gcs_setup.sh to upload to GCS."
        return res

    def search(self, query: str, project: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.client or not self.project_id or not self.engine_id:
            # Fallback to local if not configured
            return LocalJsonlSearchProvider().search(query, project, limit)

        try:
            from google.cloud import discoveryengine
            
            serving_config = self.client.serving_config_path(
                project=self.project_id,
                location=self.location,
                data_store=self.data_store_id or self.engine_id,
                serving_config="default_config",
            )

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=limit,
            )

            response = self.client.search(request)
            
            results = []
            for result in response.results:
                data = result.document.derived_struct_data
                results.append({
                    "project": project or "google-index",
                    "source_path": data.get("link", "unknown"),
                    "source_type": "google_document",
                    "title": data.get("title", "Untitled"),
                    "snippet": data.get("snippets", [{}])[0].get("snippet", "No snippet available."),
                    "score": 1.0, # Discovery Engine results are already ranked
                    "record_id": result.document.id
                })
            return results

        except Exception as e:
            # Return error as a pseudo-result or log it
            return [{"title": "Search Error", "snippet": str(e), "score": 0, "project": "error"}]
