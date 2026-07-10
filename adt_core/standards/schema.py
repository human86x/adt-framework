import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field, asdict

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

@dataclass
class Clause:
    id: str
    title: str
    text: str
    disposition: str = Disposition.PENDING
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    rationale: Optional[str] = None
    scr_ref: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Clause':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class Standard:
    id: str
    title: str
    version: str
    publisher: str
    source_url: str
    scope: str
    clauses: List[Clause] = field(default_factory=list)
    imported_at: Optional[str] = None
    imported_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # asdict already handles nested dataclasses, but we ensure it's clean
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Standard':
        data = data.copy()
        clauses_data = data.pop('clauses', [])
        clauses = [Clause.from_dict(c) for c in clauses_data]
        return cls(clauses=clauses, **{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

class StandardsSchema:
    """Schema definition and validation for Standards Layer."""

    @staticmethod
    def validate_clause(clause_data: Dict[str, Any]) -> bool:
        required = ['id', 'title', 'text', 'disposition']
        for field in required:
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
        required = ['id', 'title', 'version', 'publisher', 'source_url', 'scope', 'clauses']
        for field in required:
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



class CheckType:
    """SPEC-063 v1 check-type taxonomy for MachineReadableRule."""
    ADS_EVENT_REQUIRED = 'ads_event_required'
    PATH_JURISDICTION = 'path_jurisdiction'
    FIELD_PRESENT = 'field_present'
    VALUE_CONSTRAINT = 'value_constraint'
    SEQUENCE_REQUIRED = 'sequence_required'
    TIER_MINIMUM = 'tier_minimum'

    ALL = [
        ADS_EVENT_REQUIRED,
        PATH_JURISDICTION,
        FIELD_PRESENT,
        VALUE_CONSTRAINT,
        SEQUENCE_REQUIRED,
        TIER_MINIMUM,
    ]


class Severity:
    """SPEC-063 severity ladder for MachineReadableRule."""
    ADVISORY = 'advisory'
    REQUIRED = 'required'
    TIER_2 = 'tier_2'
    TIER_1 = 'tier_1'

    ALL = [ADVISORY, REQUIRED, TIER_2, TIER_1]


@dataclass
class RationalisedRule:
    """SPEC-063: A consolidated governance rule harmonising equivalent or
    overlapping clauses from multiple standards.

    Storage: _cortex/standards/rationalised_rules.jsonl (append-only).
    """
    id: str
    title: str
    text: str
    derived_from: List[str]
    scope: str = StandardScope.ETHICAL
    disposition: str = Disposition.PENDING
    rationale: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    scr_ref: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RationalisedRule':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MachineReadableRule:
    """SPEC-063: A computable representation of a RationalisedRule, suitable
    for runtime validation by DTCP (opt-in) and external evaluators.

    Storage: _cortex/standards/machine_readable_rules.jsonl (append-only).
    """
    id: str
    rationalised_rule: str
    check_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    severity: str = Severity.ADVISORY
    validates_specs: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    superseded_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MachineReadableRule':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def validate_rationalised_rule(data: Dict[str, Any]) -> bool:
    required = ['id', 'title', 'text', 'derived_from', 'scope', 'disposition']
    for f in required:
        if f not in data:
            logger.error(f'RationalisedRule validation failed: missing field {f}')
            return False
    if data['disposition'] not in Disposition.ALL:
        logger.error(f'RationalisedRule validation failed: invalid disposition {data["disposition"]}')
        return False
    if data['scope'] not in StandardScope.ALL:
        logger.error(f'RationalisedRule validation failed: invalid scope {data["scope"]}')
        return False
    if not isinstance(data['derived_from'], list) or not data['derived_from']:
        logger.error('RationalisedRule validation failed: derived_from must be non-empty list')
        return False
    if data['disposition'] in (Disposition.ADAPTED, Disposition.DISMISSED) and not data.get('rationale'):
        logger.error('RationalisedRule validation failed: rationale required for adapted/dismissed')
        return False
    return True


def validate_machine_readable_rule(data: Dict[str, Any]) -> bool:
    required = ['id', 'rationalised_rule', 'check_type', 'severity']
    for f in required:
        if f not in data:
            logger.error(f'MachineReadableRule validation failed: missing field {f}')
            return False
    if data['check_type'] not in CheckType.ALL:
        logger.error(f'MachineReadableRule validation failed: invalid check_type {data["check_type"]}')
        return False
    if data['severity'] not in Severity.ALL:
        logger.error(f'MachineReadableRule validation failed: invalid severity {data["severity"]}')
        return False
    return True
