"""DTGP Credential Vault.

Storage: ~/.adt-dtgp/vault/<project_id>/<ref>.enc
Encryption: OS keyring (via keyring library) if available; Fernet fallback.
Refuses to start if fallback key exists but is world-readable.

NO retrieve_credential endpoint is exposed -- credentials only leave the vault
inside driver stack frames during action execution (Phase 2).

SPEC-113 ss3.6.
"""
import hashlib
import json
import logging
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "adt-dtgp"


class VaultError(Exception):
    pass


class VaultPermissionError(VaultError):
    pass


class Vault:
    """Per-project credential vault.

    backend: "auto" (try keyring first, fallback to fernet)
             "keyring" (force OS keyring; fail if unavailable)
             "fernet" (force Fernet fallback)
    """

    def __init__(
        self,
        project_id: str,
        vault_base_dir: str,
        master_key_path: str,
        backend: str = "auto",
    ):
        self.project_id = project_id
        self.vault_dir = Path(vault_base_dir) / project_id
        self.master_key_path = Path(master_key_path)
        self.backend = backend
        self._fernet: Optional[object] = None
        self._use_keyring: bool = False

        self._init_backend()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_backend(self):
        """Determine which encryption backend to use."""
        if self.backend in ("auto", "keyring"):
            try:
                import keyring as kr
                kr.get_keyring()  # probe
                self._use_keyring = True
                logger.info("DTGP vault: using OS keyring backend")
                return
            except Exception as exc:
                if self.backend == "keyring":
                    raise VaultError(f"Keyring backend forced but unavailable: {exc}") from exc
                logger.info("Keyring unavailable (%s), falling back to Fernet", exc)

        # Fernet path
        self._check_master_key_permissions()
        self._fernet = self._load_or_create_fernet_key()
        logger.info("DTGP vault: using Fernet backend (master key: %s)", self.master_key_path)

    def _check_master_key_permissions(self):
        """Refuse to start if master.key exists and is world-readable."""
        if not self.master_key_path.exists():
            return
        mode = self.master_key_path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise VaultPermissionError(
                f"Vault master key {self.master_key_path} has insecure permissions "
                f"({oct(mode)}). Run: chmod 600 {self.master_key_path}"
            )

    def _load_or_create_fernet_key(self):
        from cryptography.fernet import Fernet
        kp = self.master_key_path
        if kp.exists():
            key = kp.read_bytes().strip()
        else:
            kp.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            # Write with 600 permissions atomically
            fd = os.open(str(kp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
            logger.info("Generated new Fernet master key at %s", kp)
        return Fernet(key)

    # ------------------------------------------------------------------
    # Vault directory management
    # ------------------------------------------------------------------

    def _ensure_vault_dir(self):
        if not self.vault_dir.exists():
            self.vault_dir.mkdir(parents=True, mode=0o700)
        else:
            self.vault_dir.chmod(0o700)

    def _enc_path(self, ref: str) -> Path:
        # Sanitise ref to safe filename characters
        safe_ref = "".join(c if c.isalnum() or c in "-_." else "_" for c in ref)
        return self.vault_dir / f"{safe_ref}.enc"

    # ------------------------------------------------------------------
    # Internal encrypt / decrypt
    # ------------------------------------------------------------------

    def _encrypt(self, material: str) -> bytes:
        raw = material.encode("utf-8")
        if self._use_keyring:
            import keyring as kr
            kr.set_password(KEYRING_SERVICE, f"{self.project_id}/{self._enc_path.name}", material)
            # Still write a marker file so we can list/detect credentials
            return b"keyring"
        return self._fernet.encrypt(raw)

    def _encrypt_to_file(self, ref: str, material: str) -> str:
        """Encrypt material and write to vault file. Returns hex hash preview."""
        self._ensure_vault_dir()
        enc_path = self._enc_path(ref)

        if self._use_keyring:
            import keyring as kr
            kr_key = f"{self.project_id}/{ref}"
            kr.set_password(KEYRING_SERVICE, kr_key, material)
            # Marker file records metadata without the credential
            meta = {
                "backend": "keyring",
                "project_id": self.project_id,
                "ref": ref,
                "kr_key": kr_key,
            }
            enc_path.write_text(json.dumps(meta))
        else:
            ciphertext = self._fernet.encrypt(material.encode("utf-8"))
            fd, tmp = tempfile.mkstemp(dir=str(self.vault_dir))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(ciphertext)
                os.chmod(tmp, 0o600)
                os.replace(tmp, str(enc_path))
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                raise

        # Return a safe hash preview (first 8 hex chars of sha256)
        h = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]
        return h

    def _decrypt_from_file(self, ref: str) -> str:
        """Decrypt and return credential material. Internal use only."""
        enc_path = self._enc_path(ref)
        if not enc_path.exists():
            raise VaultError(f"Credential not found: {ref}")

        if self._use_keyring:
            import keyring as kr
            meta = json.loads(enc_path.read_text())
            material = kr.get_password(KEYRING_SERVICE, meta["kr_key"])
            if material is None:
                raise VaultError(f"Credential not found in keyring: {ref}")
            return material
        else:
            ciphertext = enc_path.read_bytes()
            return self._fernet.decrypt(ciphertext).decode("utf-8")

    # ------------------------------------------------------------------
    # Public API (no retrieve exposed via HTTP)
    # ------------------------------------------------------------------

    def store_credential(self, ref: str, material: str) -> dict:
        """Encrypt and store credential. Returns metadata (never material)."""
        hash_preview = self._encrypt_to_file(ref, material)
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "ref": ref,
            "project_id": self.project_id,
            "created_at": created_at,
            "hash_preview": hash_preview,
            "backend": "keyring" if self._use_keyring else "fernet",
        }

    def rotate_credential(self, ref: str, new_material: str) -> dict:
        """Re-encrypt with new material. Returns rotation metadata."""
        # Read old hash for audit
        try:
            old_material = self._decrypt_from_file(ref)
            previous_hash = hashlib.sha256(old_material.encode("utf-8")).hexdigest()[:8]
        except VaultError:
            previous_hash = "unknown"

        hash_preview = self._encrypt_to_file(ref, new_material)
        rotated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "ref": ref,
            "project_id": self.project_id,
            "rotated_at": rotated_at,
            "previous_hash": previous_hash,
            "hash_preview": hash_preview,
        }

    def revoke_credential(self, ref: str) -> dict:
        """Delete credential from vault."""
        enc_path = self._enc_path(ref)
        if not enc_path.exists():
            raise VaultError(f"Credential not found: {ref}")

        if self._use_keyring:
            try:
                import keyring as kr
                meta = json.loads(enc_path.read_text())
                kr.delete_password(KEYRING_SERVICE, meta.get("kr_key", ""))
            except Exception as exc:
                logger.warning("Keyring delete for ref %s failed: %s", ref, exc)

        enc_path.unlink(missing_ok=True)
        revoked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {"ref": ref, "project_id": self.project_id, "revoked_at": revoked_at}

    def credential_exists(self, ref: str) -> bool:
        return self._enc_path(ref).exists()

    @property
    def status(self) -> str:
        """Return 'ok' or 'missing' for health endpoint."""
        try:
            self._ensure_vault_dir()
            return "ok"
        except Exception:
            return "missing"
