"""DTGP Configuration loader.

Merges host-level config (~/.adt-dtgp/config.yaml) with per-project
overrides (_cortex/dtgp/config.yaml). Works with zero config -- all values
have safe defaults.

SPEC-113 ss3.1.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DTGPConfig:
    port: int = 5003
    project_root: str = ""
    project_name: str = ""
    project_id: str = ""

    # Vault settings
    vault_dir: str = ""           # default: ~/.adt-dtgp/vault
    keyring_backend: str = "auto" # "auto" | "keyring" | "fernet"
    master_key_path: str = ""     # default: ~/.adt-dtgp/master.key (fernet fallback)

    # Lock manager
    default_lock_timeout_s: int = 30

    # Template search directories (populated post-init)
    template_dirs: list = field(default_factory=list)

    # ADS
    ads_path: str = ""

    def __post_init__(self):
        home = Path.home()
        dtgp_home = home / ".adt-dtgp"

        if not self.vault_dir:
            self.vault_dir = str(dtgp_home / "vault")
        if not self.master_key_path:
            self.master_key_path = str(dtgp_home / "master.key")
        if not self.ads_path and self.project_root:
            self.ads_path = str(
                Path(self.project_root) / "_cortex" / "ads" / "events.jsonl"
            )
        if not self.template_dirs and self.project_root:
            pr = Path(self.project_root)
            self.template_dirs = [
                str(pr / "_cortex" / "standards" / "device_types"),
                str(pr / "_cortex" / "device_types"),
            ]

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def _load_yaml(cls, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            import yaml
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def from_project_root(cls, project_root: str, **overrides) -> "DTGPConfig":
        project_root = os.path.abspath(project_root)
        project_name = os.path.basename(project_root)
        project_id = project_name.lower().replace(" ", "-")

        # 1. Host-level defaults
        host_cfg = cls._load_yaml(
            str(Path.home() / ".adt-dtgp" / "config.yaml")
        )
        # 2. Per-project overrides
        proj_cfg = cls._load_yaml(
            str(Path(project_root) / "_cortex" / "dtgp" / "config.yaml")
        )

        merged = {**host_cfg, **proj_cfg}

        cfg = cls(
            project_root=project_root,
            project_name=project_name,
            project_id=project_id,
        )

        # Apply merged YAML values
        for key in (
            "port",
            "vault_dir",
            "keyring_backend",
            "master_key_path",
            "default_lock_timeout_s",
        ):
            if key in merged:
                setattr(cfg, key, merged[key])

        # __post_init__ already ran with empty values; re-apply defaults after
        # YAML merge so we still get defaults when YAML doesn't set a field.
        cfg.__post_init__()

        # CLI / caller overrides win
        for key, val in overrides.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)

        return cfg
