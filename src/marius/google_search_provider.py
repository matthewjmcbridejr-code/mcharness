import os
import logging
from typing import List, Dict, Optional, Any
from .search_provider import SearchProvider, LocalJsonlSearchProvider

logger = logging.getLogger(__name__)

class GoogleAgentSearchProvider(SearchProvider):
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "project-b11857c2-0ddb-4154-802")
        self.location = os.getenv("GOOGLE_AGENT_SEARCH_LOCATION", "global")
        self.engine_id = os.getenv("GOOGLE_AGENT_SEARCH_ENGINE_ID", "marius-brain")
        self.data_store_id = os.getenv("GOOGLE_AGENT_SEARCH_DATA_STORE_ID", "marius-brain-warden")
        self.serving_config_id = os.getenv("GOOGLE_AGENT_SEARCH_SERVING_CONFIG", "default_config")
        
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from google.cloud import discoveryengine_v1 as discoveryengine
            self.client = discoveryengine.SearchServiceClient()
        except ImportError:
            self.client = None
        except Exception as e:
            logger.warning(f"Failed to initialize Discovery Engine client: {e}")
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
        # Google export is local export followed by a note
        local = LocalJsonlSearchProvider()
        res = local.export(project, repo_path)
        res["google_note"] = "Local JSONL generated. Use scripts/marius_brain_gcs_setup.sh to upload to GCS and scripts/marius_brain_discovery_setup.py --import to index."
        return res

    def search(self, query: str, project: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.client or not self.project_id or not self.engine_id:
            # Silent fallback to local if not configured
            return LocalJsonlSearchProvider().search(query, project, limit)

        try:
            from google.cloud import discoveryengine_v1 as discoveryengine
            
            # The search engine path
            serving_config = self.client.serving_config_path(
                project=self.project_id,
                location=self.location,
                data_store=self.data_store_id or self.engine_id,
                serving_config=self.serving_config_id,
            )

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=limit,
            )

            pager = self.client.search(request)
            
            results = []
            for result in pager:
                doc = result.document
                data = doc.derived_struct_data
                
                # Discovery Engine returns a derived_struct_data with snippets
                snippet = "No snippet available."
                if "snippets" in data and len(data["snippets"]) > 0:
                    snippet = data["snippets"][0].get("snippet", snippet)
                elif "extractive_answers" in data and len(data["extractive_answers"]) > 0:
                    snippet = data["extractive_answers"][0].get("content", snippet)

                results.append({
                    "project": project or "google-brain",
                    "source_path": data.get("link", doc.name),
                    "source_type": "google_agent_search",
                    "title": data.get("title", doc.id),
                    "snippet": snippet,
                    "score": 1.0, # Result is already ranked
                    "record_id": doc.id,
                    "resource_name": doc.name
                })
            return results

        except Exception as e:
            logger.error(f"Google Agent Search failed: {e}")
            # Fallback to local instead of returning error if possible
            return LocalJsonlSearchProvider().search(query, project, limit)
