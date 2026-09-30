"""Penyimpanan kredensial terenkripsi di disk (Windows DPAPI + Fernet fallback).

Lokasi default: ``%LOCALAPPDATA%\\skua-lite\\credentials.enc``
Password TIDAK PERNAH disimpan sebagai plaintext.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config


class NoStoredCredentials(Exception):
    """Belum ada kredensial yang tersimpan."""


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.c_void_p)]


def _setup_dpapi():
    """Siapkan prototipe fungsi Win32 sekali saja.

    Tanpa argtypes/restype, ctypes mengembalikan pointer sebagai Python int
    dan ``LocalFree`` gagal dengan OverflowError — membuat DPAPI selalu
    tampak tidak tersedia.
    """
    if platform.system() != "Windows":
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = ctypes.c_int
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = ctypes.c_int
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        return crypt32, kernel32
    except Exception:
        return None


_DPAPI = _setup_dpapi()
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class CredentialStore:
    MACHINE_KEY = "machine.key"
    CRED_FILE = "credentials.enc"

    @staticmethod
    def _default_base_dir() -> Path:
        """Pilih lokasi stabil lintas interpreter Python di Windows.

        Microsoft Store Python dapat mengarahkan LOCALAPPDATA ke:
        ``...\\Packages\\PythonSoftwareFoundation...\\LocalCache\\Local``.
        Untuk mencegah tiap interpreter punya credential store berbeda, pakai
        ``%USERPROFILE%\\AppData\\Local`` bila LOCALAPPDATA terlihat disandbox.
        """
        local_raw = os.environ.get("LOCALAPPDATA", "")
        local = Path(local_raw) if local_raw else None
        suspicious = local is not None and (
            "Packages" in local.parts or "LocalCache" in local.parts
        )
        if platform.system() == "Windows" and suspicious:
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                return Path(user_profile) / "AppData" / "Local" / config.STORAGE_DIRNAME
            return Path.home() / "AppData" / "Local" / config.STORAGE_DIRNAME
        if local is not None:
            return local / config.STORAGE_DIRNAME
        return Path.home() / ".config" / config.STORAGE_DIRNAME

    def __init__(self, base_dir: Path | None = None) -> None:
        base = self._default_base_dir() if base_dir is None else Path(base_dir)
        self.base_dir = base
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cred_file = self.base_dir / self.CRED_FILE
        self.machine_key_file = self.base_dir / self.MACHINE_KEY
        if base_dir is None and not self.cred_file.exists():
            self._try_migrate_ms_store_credentials()

    def _try_migrate_ms_store_credentials(self) -> None:
        """Migrasi credential DPAPI dari sandbox Python Microsoft Store.

        DPAPI terikat ke user Windows, bukan proses/interpreter. Karena itu
        ciphertext dari Python Store aman untuk disalin ke lokasi canonical.
        Hanya container DPAPI valid yang dimigrasikan.
        """
        if platform.system() != "Windows" or _DPAPI is None:
            return
        user_profile = os.environ.get("USERPROFILE")
        if not user_profile:
            return
        packages = Path(user_profile) / "AppData" / "Local" / "Packages"
        if not packages.exists():
            return
        pattern = "PythonSoftwareFoundation.Python.*_*/LocalCache/Local/skua-lite/credentials.enc"
        for legacy in packages.glob(pattern):
            try:
                container = json.loads(legacy.read_text(encoding="utf-8"))
                if container.get("engine") != "dpapi":
                    continue
                raw_blob = base64.b64decode(container.get("data", ""))
                if self._dpapi_unprotect(raw_blob) is None:
                    continue
                self.cred_file.write_bytes(legacy.read_bytes())
                return
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Windows DPAPI (prioritas pertama bila Windows)
    # ------------------------------------------------------------------
    def _dpapi_protect(self, data: bytes) -> bytes | None:
        if _DPAPI is None:
            return None
        crypt32, kernel32 = _DPAPI
        try:
            in_buf = ctypes.create_string_buffer(data)
            in_blob = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.c_void_p))
            out_blob = _DATA_BLOB()

            res = crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                None, None, None, None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out_blob),
            )
            if not res:
                return None
            try:
                return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
            finally:
                kernel32.LocalFree(out_blob.pbData)
        except Exception:
            return None

    def _dpapi_unprotect(self, data: bytes) -> bytes | None:
        if _DPAPI is None:
            return None
        crypt32, kernel32 = _DPAPI
        try:
            in_buf = ctypes.create_string_buffer(data)
            in_blob = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.c_void_p))
            out_blob = _DATA_BLOB()

            res = crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None, None, None, None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out_blob),
            )
            if not res:
                return None
            try:
                return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
            finally:
                kernel32.LocalFree(out_blob.pbData)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Fernet + PBKDF2 (fallback berdasar entropy mesin)
    # ------------------------------------------------------------------
    def _machine_entropy(self) -> bytes:
        if self.machine_key_file.exists():
            return self.machine_key_file.read_bytes()
        entropy = os.urandom(32)
        self.machine_key_file.write_bytes(entropy)
        return entropy

    def _fernet(self) -> Fernet:
        salt = self._machine_entropy()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(salt))
        return Fernet(key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save(self, username: str, password: str) -> None:
        payload = json.dumps({"u": username, "p": password}).encode("utf-8")
        blob = self._dpapi_protect(payload)
        if blob is not None:
            container = {"engine": "dpapi", "data": base64.b64encode(blob).decode()}
        else:
            fer = self._fernet()
            token = fer.encrypt(payload)
            container = {"engine": "fernet", "data": token.decode()}
        self.cred_file.write_text(json.dumps(container), encoding="utf-8")

    def load(self) -> tuple[str, str]:
        if not self.cred_file.exists():
            raise NoStoredCredentials(f"file {self.cred_file} belum ada")
        try:
            container = json.loads(self.cred_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise NoStoredCredentials(f"file kredensial rusak: {e}") from e

        engine = container.get("engine")
        data_str = container.get("data", "")
        if engine == "dpapi":
            raw_blob = base64.b64decode(data_str)
            dec = self._dpapi_unprotect(raw_blob)
            if dec is None:
                raise NoStoredCredentials("DPAPI gagal mendeskripsi (mesin berbeda?)")
        elif engine == "fernet":
            fer = self._fernet()
            dec = fer.decrypt(data_str.encode())
        else:
            raise NoStoredCredentials(f"engine kripto tidak dikenal: {engine}")

        body = json.loads(dec.decode("utf-8"))
        return str(body["u"]), str(body["p"])

    def exists(self) -> bool:
        return self.cred_file.exists()

    def clear(self) -> None:
        if self.cred_file.exists():
            self.cred_file.unlink()


class MultiAccountStore:
    """Simpan beberapa akun terenkripsi; satu menjadi 'aktif'.

    Format file ``accounts.enc``:
      {
        "active": "username1",
        "accounts": {
          "username1": <encrypted-blob-same-format-as-CredentialStore>,
          "username2": <encrypted-blob>
        }
      }

    Enkripsi per-akun memakai mesin yang sama dengan CredentialStore
    (DPAPI bila tersedia, Fernet sebagai fallback). Username disimpan
    sebagai kunci plaintext (bukan rahasia); hanya password yang terenkripsi.
    """

    ACCOUNTS_FILE = "accounts.enc"

    def __init__(self, base_dir: Path | None = None) -> None:
        self._store = CredentialStore(base_dir=base_dir)
        self.base_dir = self._store.base_dir
        self.accounts_file = self.base_dir / self.ACCOUNTS_FILE

    # ---------------------------------------------------------------- internal

    def _load_raw(self) -> dict:
        if not self.accounts_file.exists():
            return {"active": None, "accounts": {}}
        try:
            return json.loads(self.accounts_file.read_text(encoding="utf-8"))
        except Exception:
            return {"active": None, "accounts": {}}

    def _save_raw(self, data: dict) -> None:
        self.accounts_file.write_text(json.dumps(data), encoding="utf-8")

    def _encrypt_password(self, password: str) -> dict:
        payload = password.encode("utf-8")
        blob = self._store._dpapi_protect(payload)
        if blob is not None:
            return {"engine": "dpapi", "data": base64.b64encode(blob).decode()}
        fer = self._store._fernet()
        token = fer.encrypt(payload)
        return {"engine": "fernet", "data": token.decode()}

    def _decrypt_password(self, container: dict) -> str:
        engine = container.get("engine")
        data_str = container.get("data", "")
        if engine == "dpapi":
            raw_blob = base64.b64decode(data_str)
            dec = self._store._dpapi_unprotect(raw_blob)
            if dec is None:
                raise NoStoredCredentials("DPAPI gagal mendeskripsi")
            return dec.decode("utf-8")
        if engine == "fernet":
            fer = self._store._fernet()
            return fer.decrypt(data_str.encode()).decode("utf-8")
        raise NoStoredCredentials(f"engine tidak dikenal: {engine}")

    # ---------------------------------------------------------------- public API

    def add_account(self, username: str, password: str) -> None:
        """Tambah atau perbarui akun; set sebagai aktif jika belum ada akun lain."""
        data = self._load_raw()
        data["accounts"][username] = self._encrypt_password(password)
        if data["active"] is None:
            data["active"] = username
        self._save_raw(data)

    def remove_account(self, username: str) -> bool:
        """Hapus akun; kembalikan False bila tidak ditemukan."""
        data = self._load_raw()
        if username not in data["accounts"]:
            return False
        del data["accounts"][username]
        if data["active"] == username:
            remaining = list(data["accounts"].keys())
            data["active"] = remaining[0] if remaining else None
        self._save_raw(data)
        return True

    def list_usernames(self) -> list[str]:
        """Daftar username yang tersimpan (tanpa password)."""
        data = self._load_raw()
        return list(data["accounts"].keys())

    def active_username(self) -> str | None:
        """Username akun aktif saat ini."""
        return self._load_raw().get("active")

    def set_active(self, username: str) -> None:
        """Ubah akun aktif; error bila username tidak ada."""
        data = self._load_raw()
        if username not in data["accounts"]:
            raise NoStoredCredentials(f"akun '{username}' tidak ditemukan")
        data["active"] = username
        self._save_raw(data)

    def load_active(self) -> tuple[str, str]:
        """Kembalikan (username, password) akun aktif."""
        data = self._load_raw()
        active = data.get("active")
        if not active or active not in data.get("accounts", {}):
            raise NoStoredCredentials("belum ada akun aktif yang tersimpan")
        password = self._decrypt_password(data["accounts"][active])
        return active, password

    def load(self, username: str) -> tuple[str, str]:
        """Kembalikan (username, password) untuk username tertentu."""
        data = self._load_raw()
        if username not in data.get("accounts", {}):
            raise NoStoredCredentials(f"akun '{username}' tidak ditemukan")
        password = self._decrypt_password(data["accounts"][username])
        return username, password

    def has_accounts(self) -> bool:
        return bool(self._load_raw().get("accounts"))
