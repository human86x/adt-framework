import os
import json
import logging
from typing import Dict, Any, List, Optional
from .schema import StandardsSchema

logger = logging.getLogger(__name__)

class StandardsRegistry:
    """Manages a collection of standards stored in a JSON file."""

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._ensure_registry_exists()

    def _ensure_registry_exists(self):
        if not os.path.exists(self.registry_path):
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, 'w') as f:
                json.dump({"standards": {}}, f, indent=2)

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.registry_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'Failed to load standards registry: {e}')
            return {"standards": {}}

    def save(self, data: Dict[str, Any]):
        try:
            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f'Failed to save standards registry: {e}')

    def get_all_standards(self) -> List[Dict[str, Any]]:
        data = self.load()
        return list(data.get("standards", {}).values())

    def get_standard(self, standard_id: str) -> Optional[Dict[str, Any]]:
        data = self.load()
        return data.get("standards", {}).get(standard_id)

    def add_standard(self, standard: Dict[str, Any]):
        if not StandardsSchema.validate_standard(standard):
            raise ValueError('Invalid standard data')
        
        data = self.load()
        data["standards"][standard['id']] = standard
        self.save(data)

    def update_clause(self, standard_id: str, clause_id: str, update_data: Dict[str, Any]):
        data = self.load()
        if standard_id not in data["standards"]:
            raise ValueError(f'Standard {standard_id} not found')
        
        standard = data["standards"][standard_id]
        for i, clause in enumerate(standard['clauses']):
            if clause['id'] == clause_id:
                standard['clauses'][i].update(update_data)
                # Re-validate
                if not StandardsSchema.validate_clause(standard['clauses'][i]):
                    raise ValueError('Invalid clause data after update')
                self.save(data)
                return
        
        raise ValueError(f'Clause {clause_id} not found in standard {standard_id}')
