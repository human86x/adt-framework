import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union

logger = logging.getLogger(__name__)

class Disposition:
    PENDING = 'pending'
    ADOPTED = 'adopted'
    ADAPTED = 'adapted'
    DISMISSED = 'dismissed'
    
    ALL = [PENDING, ADOPTED, ADAPTED, DISMISSED]

class StandardScope:
    ETHICAL = 'ethical'
    REGULATORY = 'regulatory'
    OPERATIONAL = 'operational'
    INTERNAL_CODEX = 'internal_codex'
    
    ALL = [ETHICAL, REGULATORY, OPERATIONAL, INTERNAL_CODEX]

class StandardsSchema:
    """Schema definition and validation for Standards Layer."""

    STANDARD_REQUIRED_FIELDS = [
        'id',
        'title',
        'version',
        'publisher',
        'source_url',
        'scope',
        'imported_at',
        'imported_by',
        'clauses'
    ]

    CLAUSE_REQUIRED_FIELDS = [
        'id',
        'title',
        'text',
        'disposition',
        'decided_at',
        'decided_by'
    ]

    @staticmethod
    def validate_clause(clause_data: Dict[str, Any]) -> bool:
        for field in StandardsSchema.CLAUSE_REQUIRED_FIELDS:
            if field not in clause_data:
                logger.error(f'Clause validation failed: missing field {field}')
                return False
        
        if clause_data['disposition'] not in Disposition.ALL:
            logger.error(f'Clause validation failed: invalid disposition {clause_data["disposition"]}')
            return False
            
        if clause_data['disposition'] in [Disposition.ADAPTED, Disposition.DISMISSED]:
            if not clause_data.get('rationale'):
                logger.error('Clause validation failed: rationale required for adapted/dismissed')
                return False
                
        return True

    @staticmethod
    def validate_standard(standard_data: Dict[str, Any]) -> bool:
        for field in StandardsSchema.STANDARD_REQUIRED_FIELDS:
            if field not in standard_data:
                logger.error(f'Standard validation failed: missing field {field}')
                return False
                
        if standard_data['scope'] not in StandardScope.ALL:
            logger.error(f'Standard validation failed: invalid scope {standard_data["scope"]}')
            return False
            
        if not isinstance(standard_data['clauses'], list):
            return False
            
        for clause in standard_data['clauses']:
            if not StandardsSchema.validate_clause(clause):
                return False
                
        return True

    @staticmethod
    def create_clause(
        id: str,
        title: str,
        text: str,
        tags: Optional[List[str]] = None,
        disposition: str = Disposition.PENDING,
        rationale: Optional[str] = None,
        decided_by: str = 'SYSTEM',
        **kwargs
    ) -> Dict[str, Any]:
        clause = {
            'id': id,
            'title': title,
            'text': text,
            'tags': tags or [],
            'disposition': disposition,
            'rationale': rationale,
            'decided_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'decided_by': decided_by,
            'scr_ref': kwargs.get('scr_ref')
        }
        clause.update(kwargs)
        return clause

    @staticmethod
    def create_standard(
        id: str,
        title: str,
        version: str,
        publisher: str,
        source_url: str,
        scope: str,
        imported_by: str = 'SYSTEM',
        clauses: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        standard = {
            'id': id,
            'title': title,
            'version': version,
            'publisher': publisher,
            'source_url': source_url,
            'scope': scope,
            'imported_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'imported_by': imported_by,
            'clauses': clauses or []
        }
        standard.update(kwargs)
        return standard
