import os
import sys
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DTTPConfig:
    port: int = 5002
    mode: str = 'development'
    ads_path: str = ''
    specs_config: str = ''
    jurisdictions_config: str = ''
    project_root: str = ''
    project_name: str = ''
    enforcement_mode: str = 'development'
    access_token: Optional[str] = None
    is_framework_project: bool = False

    @staticmethod
    def get_user_config_dir() -> str:
        if sys.platform == 'win32':
            return os.path.join(os.environ.get('APPDATA', ''), 'adt')
        elif sys.platform == 'darwin':
            return os.path.expanduser('~/Library/Application Support/adt')
        else:
            return os.path.expanduser('~/.adt')

    @classmethod
    def from_env(cls, defaults: dict = None) -> 'DTTPConfig':
        d = defaults or {}
        return cls(
            port=int(os.environ.get('DTTP_PORT', d.get('port', 5002))),
            mode=os.environ.get('DTTP_MODE', d.get('mode', 'development')),
            ads_path=os.environ.get('DTTP_ADS_PATH', d.get('ads_path', '')),
            specs_config=os.environ.get('DTTP_SPECS_CONFIG', d.get('specs_config', '')),
            jurisdictions_config=os.environ.get('DTTP_JURISDICTIONS_CONFIG', d.get('jurisdictions_config', '')),
            project_root=os.environ.get('DTTP_PROJECT_ROOT', d.get('project_root', '')),
            project_name=os.environ.get('DTTP_PROJECT_NAME', d.get('project_name', '')),
            enforcement_mode=os.environ.get('DTTP_ENFORCEMENT_MODE', d.get('enforcement_mode', 'development')),
            access_token=os.environ.get('ADT_ACCESS_TOKEN', d.get('access_token')),
            is_framework_project=os.environ.get('ADT_IS_FRAMEWORK', 'false').lower() == 'true'
        )

    @classmethod
    def from_project_root(cls, project_root: str, **overrides) -> 'DTTPConfig':
        project_root = os.path.abspath(project_root)
        
        # Check if it is the framework project
        # This is a bit heuristic but works for now: check if it contains adt_core
        is_framework = os.path.exists(os.path.join(project_root, "adt_core"))
        
        config = cls(
            project_root=project_root,
            project_name=os.path.basename(project_root),
            ads_path=os.path.join(project_root, '_cortex', 'ads', 'events.jsonl'),
            specs_config=os.path.join(project_root, 'config', 'specs.json'),
            jurisdictions_config=os.path.join(project_root, 'config', 'jurisdictions.json'),
            enforcement_mode='development',
            is_framework_project=is_framework
        )
        
        # Merge from config/dttp.json if it exists
        dttp_json = os.path.join(project_root, "config", "dttp.json")
        if os.path.exists(dttp_json):
            try:
                import json
                with open(dttp_json, "r") as f:
                    data = json.load(f)
                    if "port" in data: config.port = data["port"]
                    if "name" in data: config.project_name = data["name"]
                    if "mode" in data: config.mode = data["mode"]
                    if "enforcement_mode" in data: config.enforcement_mode = data["enforcement_mode"]
            except: pass

        for key, val in overrides.items():
            if hasattr(config, key):
                setattr(config, key, val)
        return config
