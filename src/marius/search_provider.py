import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from .search_export import export_project_context

class SearchProvider:
    def status(self) -> Dict[str, Any]:
        raise NotImplementedError()

    def export(self, project: str, repo_path: str) -> Dict[str, Any]:
        raise NotImplementedError()

    def search(self, query: str, project: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError()

class LocalJsonlSearchProvider(SearchProvider):
    def __init__(self, exports_dir: Optional[Path] = None):
        self.exports_dir = exports_dir or Path.home() / ".local" / "share" / "marius" / "brain" / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> Dict[str, Any]:
        exports = []
        if self.exports_dir.exists():
            for f in self.exports_dir.glob("*.jsonl"):
                exports.append({
                    "project": f.stem,
                    "size_bytes": f.stat().st_size,
                    "updated_at": Path(f).stat().st_mtime
                })
        return {
            "provider": "local",
            "exports_dir": str(self.exports_dir),
            "exports": exports
        }

    def export(self, project: str, repo_path: str) -> Dict[str, Any]:
        output_file = export_project_context(project, repo_path, str(self.exports_dir))
        return {
            "ok": True,
            "project": project,
            "output_file": str(output_file),
            "size_bytes": output_file.stat().st_size
        }

    def search(self, query: str, project: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        results = []
        query_terms = query.lower().split()
        
        target_files = []
        if project:
            target_files = [self.exports_dir / f"{project}.jsonl"]
        else:
            target_files = list(self.exports_dir.glob("*.jsonl"))
            
        for export_file in target_files:
            if not export_file.exists():
                continue
                
            with open(export_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        text = record.get("text", "").lower()
                        title = record.get("title", "").lower()
                        
                        score = 0
                        for term in query_terms:
                            if term in title:
                                score += 10
                            if term in text:
                                score += text.count(term)
                                
                        if score > 0:
                            # Create snippet
                            full_text = record.get("text", "")
                            snippet = ""
                            if query_terms:
                                first_term = query_terms[0]
                                idx = full_text.lower().find(first_term)
                                if idx != -1:
                                    start = max(0, idx - 50)
                                    end = min(len(full_text), idx + 150)
                                    snippet = full_text[start:end].replace("\n", " ")
                                else:
                                    snippet = full_text[:200].replace("\n", " ")
                            else:
                                snippet = full_text[:200].replace("\n", " ")
                                
                            results.append({
                                "project": record.get("project"),
                                "source_path": record.get("source_path"),
                                "source_type": record.get("source_type"),
                                "title": record.get("title"),
                                "snippet": snippet,
                                "score": float(score),
                                "record_id": record.get("id")
                            })
                    except Exception:
                        continue
                        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

def get_search_provider() -> SearchProvider:
    # Factory for search provider
    provider_type = os.getenv("MARIUS_SEARCH_PROVIDER", "local").lower()
    if provider_type == "google":
        try:
            from .google_search_provider import GoogleAgentSearchProvider
            return GoogleAgentSearchProvider()
        except ImportError:
            return LocalJsonlSearchProvider()
    return LocalJsonlSearchProvider()
