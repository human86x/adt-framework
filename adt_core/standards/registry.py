import os
import json
import logging
from typing import Dict, Any, List, Optional
from .schema import StandardsSchema, Standard, Clause, Disposition

logger = logging.getLogger(__name__)

class StandardsRegistry:
    """Manages standards stored in _cortex/standards/ as individual JSON files."""

    def __init__(self, standards_dir: str):
        self.standards_dir = standards_dir
        self.index_path = os.path.join(standards_dir, 'index.json')
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        if not os.path.exists(self.standards_dir):
            os.makedirs(self.standards_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild index.json from standard files in the directory."""
        standards_meta = []
        if not os.path.exists(self.standards_dir):
            return

        for filename in os.listdir(self.standards_dir):
            if filename.endswith('.json') and filename != 'index.json' and filename != 'registry.json':
                try:
                    file_path = os.path.join(self.standards_dir, filename)
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        standard = Standard.from_dict(data)
                        
                        summary = {
                            "total": len(standard.clauses),
                            "pending": len([c for c in standard.clauses if c.disposition == Disposition.PENDING]),
                            "adopted": len([c for c in standard.clauses if c.disposition == Disposition.ADOPTED]),
                            "adapted": len([c for c in standard.clauses if c.disposition == Disposition.ADAPTED]),
                            "dismissed": len([c for c in standard.clauses if c.disposition == Disposition.DISMISSED])
                        }
                        
                        standards_meta.append({
                            "id": standard.id,
                            "title": standard.title,
                            "version": standard.version,
                            "file": filename,
                            "status_summary": summary
                        })
                except Exception as e:
                    logger.error(f'Failed to parse {filename}: {e}')
        
        # Sort by ID for determinism
        standards_meta.sort(key=lambda x: x['id'])
        
        with open(self.index_path, 'w') as f:
            json.dump({"standards": standards_meta}, f, indent=2)

    def get_all_standards(self) -> List[Dict[str, Any]]:
        """Compatibility method: returns list of metadata from index."""
        return self.get_index()

    def get_index(self) -> List[Dict[str, Any]]:
        try:
            if not os.path.exists(self.index_path):
                self._rebuild_index()
            with open(self.index_path, 'r') as f:
                return json.load(f).get("standards", [])
        except Exception as e:
            logger.error(f'Failed to load index: {e}')
            return []

    def get_standard(self, standard_id: str) -> Optional[Standard]:
        index = self.get_index()
        for entry in index:
            if entry['id'] == standard_id:
                file_path = os.path.join(self.standards_dir, entry['file'])
                try:
                    with open(file_path, 'r') as f:
                        return Standard.from_dict(json.load(f))
                except Exception as e:
                    logger.error(f'Failed to load standard {standard_id}: {e}')
                    return None
        
        # Fallback: check if file exists directly
        file_path = os.path.join(self.standards_dir, f"{standard_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return Standard.from_dict(json.load(f))
            except Exception as e:
                logger.error(f'Failed to load standard {standard_id} (fallback): {e}')
                return None
                
        return None

    def add_standard(self, standard_data: Dict[str, Any]):
        """Compatibility method: accepts dict, validates, saves."""
        if not StandardsSchema.validate_standard(standard_data):
            raise ValueError('Invalid standard data')
        
        standard = Standard.from_dict(standard_data)
        self.save_standard(standard)

    def save_standard(self, standard: Standard):
        filename = f"{standard.id}.json"
        file_path = os.path.join(self.standards_dir, filename)
        
        with open(file_path, 'w') as f:
            json.dump(standard.to_dict(), f, indent=2)
        
        self._rebuild_index()

    def update_clause(self, standard_id: str, clause_id: str, update_data: Dict[str, Any]) -> bool:
        standard = self.get_standard(standard_id)
        if not standard:
            return False
            
        found = False
        for clause in standard.clauses:
            if clause.id == clause_id:
                # Update fields
                for k, v in update_data.items():
                    if hasattr(clause, k):
                        setattr(clause, k, v)
                
                # Validation check
                if not StandardsSchema.validate_clause(clause.to_dict()):
                    raise ValueError('Invalid clause data after update')
                    
                found = True
                break
        
        if found:
            self.save_standard(standard)
            return True
        return False
