from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol

LPBYTE = ctypes.POINTER(wintypes.BYTE)

class CredentialStore(Protocol):
    def set_password(self, target: str, secret: str) -> None: ...
    def get_password(self, target: str) -> str | None: ...
    def delete_password(self, target: str) -> None: ...


class CredentialUnavailableError(RuntimeError):
    pass


class WindowsCredentialStore:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CredentialUnavailableError("Windows Credential Manager is only available on Windows.")
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    def set_password(self, target: str, secret: str) -> None:
        blob = secret.encode("utf-16-le")
        credential = CREDENTIAL()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(ctypes.create_string_buffer(blob), LPBYTE)
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "CLM Assistant Desktop"
        if not self.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise CredentialUnavailableError(f"CredWriteW failed: {ctypes.get_last_error()}")

    def get_password(self, target: str) -> str | None:
        credential_pointer = ctypes.POINTER(CREDENTIAL)()
        if not self.advapi32.CredReadW(target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(credential_pointer)):
            return None
        try:
            credential = credential_pointer.contents
            data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return data.decode("utf-16-le")
        finally:
            self.advapi32.CredFree(credential_pointer)

    def delete_password(self, target: str) -> None:
        self.advapi32.CredDeleteW(target, self.CRED_TYPE_GENERIC, 0)


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def default_credential_store() -> CredentialStore:
    return WindowsCredentialStore()
