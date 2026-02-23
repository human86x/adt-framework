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
        )

    @classmethod
    def from_project_root(cls, project_root: str, **overrides) -> 'DTTPConfig':
        project_root = os.path.abspath(project_root)
        config = cls(
            project_root=project_root,
            project_name=os.path.basename(project_root),
            ads_path=os.path.join(project_root, '_cortex', 'ads', 'events.jsonl'),
            specs_config=os.path.join(project_root, 'config', 'specs.json'),
            jurisdictions_config=os.path.join(project_root, 'config', 'jurisdictions.json'),
            enforcement_mode='development',
        )
        for key, val in overrides.items():
            if hasattr(config, key):
                setattr(config, key, val)
        return config
