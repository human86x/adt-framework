import os
from dataclasses import dataclass, field


@dataclass
class DTTPConfig:
    """Configuration for the standalone DTTP service."""
    port: int = 5002
    mode: str = "development"
    ads_path: str = ""
    specs_config: str = ""
    jurisdictions_config: str = ""
    project_root: str = ""
    project_name: str = ""

    @classmethod
    def from_env(cls, defaults: dict = None) -> "DTTPConfig":
        """Load config from environment variables with optional defaults dict."""
        d = defaults or {}
        return cls(
            port=int(os.environ.get("DTTP_PORT", d.get("port", 5002))),
            mode=os.environ.get("DTTP_MODE", d.get("mode", "development")),
            ads_path=os.environ.get("DTTP_ADS_PATH", d.get("ads_path", "")),
            specs_config=os.environ.get("DTTP_SPECS_CONFIG", d.get("specs_config", "")),
            jurisdictions_config=os.environ.get("DTTP_JURISDICTIONS_CONFIG", d.get("jurisdictions_config", "")),
            project_root=os.environ.get("DTTP_PROJECT_ROOT", d.get("project_root", "")),
            project_name=os.environ.get("DTTP_PROJECT_NAME", d.get("project_name", "")),
        )

    @classmethod
    def from_project_root(cls, project_root: str, **overrides) -> "DTTPConfig":
        """Create config by auto-detecting paths from a project root directory."""
        project_root = os.path.abspath(project_root)
        config = cls(
            project_root=project_root,
            project_name=os.path.basename(project_root),
            ads_path=os.path.join(project_root, "_cortex", "ads", "events.jsonl"),
            specs_config=os.path.join(project_root, "config", "specs.json"),
            jurisdictions_config=os.path.join(project_root, "config", "jurisdictions.json"),
        )
        for key, val in overrides.items():
            if hasattr(config, key):
                setattr(config, key, val)
        return config
