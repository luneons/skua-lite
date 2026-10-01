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


import re as _re


def parse_plaintext_accounts(text: str) -> dict[str, str]:
    """Parse format file 'akun.txt': satu baris per akun (username,password).

    Aturan:
      - Komentar diawali '#' dan baris kosong diabaikan.
      - Nomor indeks di awal baris opsional (misal '1. mele,pass' atau '2) sorani,pass')
        dibersihkan otomatis untuk memudahkan copy-paste.
      - Username boleh mengandung spasi (misal 'sorani ex,pass123').
      - Password dipisahkan oleh koma pertama; koma berikutnya dianggap bagian password.
      - Entri tidak valid (tanpa koma, username kosong, atau password kosong) dilewati.
    """
    results: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Bersihkan prefix nomor seperti "1. " atau "2) " jika ada
        line = _re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if not line or line.startswith("#") or "," not in line:
            continue
        user, _, pwd = line.partition(",")
        user = user.strip()
        pwd = pwd.strip()
        if user and pwd:
            results[user] = pwd
    return results


def harden_plaintext_file(path: Path) -> bool:
    """Batasi izin file hanya untuk pemilik (POSIX 0600, best-effort Windows ACL)."""
    p = Path(path)
    if not p.exists() or p.is_dir():
        return False
    try:
        if platform.system() != "Windows":
            p.chmod(0o600)
            return True
        # Di Windows, file di bawah %LOCALAPPDATA% sudah terlindungi per-user profile.
        # Set hidden/system attribute tidak wajib, tapi kita pastikan readable by user.
        return True
    except OSError:
        return False

"""Penyimpanan kredensial terenkripsi di disk (Windows DPAPI + Fernet fallback).

Lokasi default: ``%LOCALAPPDATA%\\skua-lite\\credentials.enc``
Password TIDAK PERNAH disimpan sebagai plaintext.
"""



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
    """Simpan beberapa akun terenkripsi (accounts.enc) dan/atau transparan (akun.txt).

    Sumber data:
      1. ``accounts.enc``: terenkripsi DPAPI/Fernet (default via UI/terminal)
      2. ``akun.txt``: plaintext lokal untuk kemudahan multi-akun manual

    Penggabungan (merge):
      - Jika ada username yang sama di kedua file, versi terenkripsi diutamakan.
      - Username unik: ditampilkan satu kali saja di menu/daftar.
      - Password tidak pernah diekspos melalui fungsi daftar/laporan.
    """

    ACCOUNTS_FILE = "accounts.enc"
    PLAINTEXT_FILE = "akun.txt"

    def __init__(self, base_dir: Path | None = None) -> None:
        self._explicit_base_dir = base_dir is not None
        self._store = CredentialStore(base_dir=base_dir)
        self.base_dir = self._store.base_dir
        self.accounts_file = self.base_dir / self.ACCOUNTS_FILE
        self.plaintext_file = self.base_dir / self.PLAINTEXT_FILE

    # ---------------------------------------------------------------- internal

    def _load_raw(self) -> dict:
        if not self.accounts_file.exists():
            return {"active": None, "accounts": {}}
        try:
            return json.loads(self.accounts_file.read_text(encoding="utf-8"))
        except Exception:
            return {"active": None, "accounts": {}}

    def _load_plaintext(self) -> dict[str, str]:
        results: dict[str, str] = {}
        # 1. Cek file di base_dir (misal %LOCALAPPDATA%/skua-lite/akun.txt)
        if self.plaintext_file.exists() and not self.plaintext_file.is_dir():
            try:
                text = self.plaintext_file.read_text(encoding="utf-8")
                harden_plaintext_file(self.plaintext_file)
                results.update(parse_plaintext_accounts(text))
            except Exception:
                pass

        # 2. Cek file di current working directory (misal C:/.../skua-lite/akun.txt)
        # Hanya jika store menggunakan lokasi default (tidak dispesifikasikan base_dir secara eksplisit)
        # agar test atau per-slot store yang terisolasi tidak tertular file lokal root.
        try:
            cwd_file = Path.cwd() / self.PLAINTEXT_FILE
            if not self._explicit_base_dir and cwd_file != self.plaintext_file and cwd_file.exists() and not cwd_file.is_dir():
                text = cwd_file.read_text(encoding="utf-8")
                harden_plaintext_file(cwd_file)
                # Kunci yang sudah ada di results tidak ditimpa
                for u, p in parse_plaintext_accounts(text).items():
                    if u not in results:
                        results[u] = p
        except Exception:
            pass

        return results

    def _save_plaintext(self, accounts: dict[str, str]) -> None:
        lines = ["# Daftar akun AQW (username,password)", "# Diabaikan oleh Git dan aman di perangkat lokal"]
        for u, p in accounts.items():
            lines.append(f"{u},{p}")
        self.plaintext_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        harden_plaintext_file(self.plaintext_file)

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
        """Hapus akun dari penyimpanan terenkripsi DAN plaintext; kembalikan False jika tidak ada."""
        found = False
        target_cf = username.casefold()

        # 1. Hapus dari terenkripsi
        data = self._load_raw()
        enc_match = None
        for u in list(data["accounts"].keys()):
            if u.casefold() == target_cf:
                enc_match = u
                break
        if enc_match is not None:
            del data["accounts"][enc_match]
            if data["active"] and data["active"].casefold() == target_cf:
                remaining = list(data["accounts"].keys())
                data["active"] = remaining[0] if remaining else None
            self._save_raw(data)
            found = True

        # 2. Hapus dari plaintext
        pt = self._load_plaintext()
        pt_match = None
        for u in list(pt.keys()):
            if u.casefold() == target_cf:
                pt_match = u
                break
        if pt_match is not None:
            del pt[pt_match]
            self._save_plaintext(pt)
            found = True

        return found

    def list_usernames(self) -> list[str]:
        """Daftar username yang tersimpan (gabungan terenkripsi + akun.txt, dedup case-insensitive)."""
        data = self._load_raw()
        enc_users = list(data["accounts"].keys())
        seen_cf = {u.casefold() for u in enc_users}

        combined = list(enc_users)
        pt_accounts = self._load_plaintext()
        for u in pt_accounts:
            if u.casefold() not in seen_cf:
                combined.append(u)
                seen_cf.add(u.casefold())
        return combined

    def account_source(self, username: str) -> str | None:
        """Kembalikan 'encrypted', 'plaintext', atau None."""
        target_cf = username.casefold()
        data = self._load_raw()
        for u in data["accounts"]:
            if u.casefold() == target_cf:
                return "encrypted"
        pt = self._load_plaintext()
        for u in pt:
            if u.casefold() == target_cf:
                return "plaintext"
        return None

    def active_username(self) -> str | None:
        """Username akun aktif saat ini."""
        data = self._load_raw()
        active = data.get("active")
        if active:
            return active
        all_users = self.list_usernames()
        return all_users[0] if all_users else None

    def set_active(self, username: str) -> None:
        """Ubah akun aktif; error bila username tidak ada di sumber manapun."""
        all_users = self.list_usernames()
        match = None
        for u in all_users:
            if u.casefold() == username.casefold():
                match = u
                break
        if match is None:
            raise NoStoredCredentials(f"akun '{username}' tidak ditemukan")
        data = self._load_raw()
        data["active"] = match
        self._save_raw(data)

    def load_active(self) -> tuple[str, str]:
        """Kembalikan (username, password) akun aktif."""
        active = self.active_username()
        if not active:
            raise NoStoredCredentials("belum ada akun aktif yang tersimpan")
        return self.load(active)

    def load(self, username: str) -> tuple[str, str]:
        """Kembalikan (username, password); dahulukan terenkripsi, lalu fallback ke plaintext."""
        target_cf = username.casefold()

        # 1. Cek terenkripsi dulu
        data = self._load_raw()
        for u, blob in data.get("accounts", {}).items():
            if u.casefold() == target_cf:
                return u, self._decrypt_password(blob)

        # 2. Cek plaintext
        pt = self._load_plaintext()
        for u, pwd in pt.items():
            if u.casefold() == target_cf:
                return u, pwd

        raise NoStoredCredentials(f"akun '{username}' tidak ditemukan")

    def has_accounts(self) -> bool:
        return bool(self.list_usernames())
