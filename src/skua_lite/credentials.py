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
