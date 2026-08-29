from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agent.credentials import CredentialStore, CredentialUnavailableError, default_credential_store
from app.db.session import SessionLocal
from app.models import ProviderSetting

OPENAI_CREDENTIAL_TARGET = "CLM Assistant Desktop OpenAI API Key"
DEFAULT_MODEL = "gpt-5.6-luna"


class ProviderSettingsService:
    def __init__(self, credential_store: CredentialStore | None = None, db: Session | None = None) -> None:
        self.credential_store = credential_store
        self.db = db

    def get_mode(self) -> str:
        return self._get_setting("provider_mode") or "local"

    def set_mode(self, mode: str) -> None:
        if mode not in {"local", "openai"}:
            raise ValueError("PROVIDER_MODE_UNSUPPORTED")
        self._set_setting("provider_mode", mode)

    def get_model(self) -> str:
        return self._get_setting("openai_model") or DEFAULT_MODEL

    def set_model(self, model: str) -> None:
        cleaned = model.strip()
        if not cleaned or len(cleaned) > 120:
            raise ValueError("MODEL_ID_INVALID")
        self._set_setting("openai_model", cleaned)

    def api_key_configured(self) -> bool:
        return self.get_api_key() is not None

    def set_api_key(self, api_key: str) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            raise ValueError("API_KEY_REQUIRED")
        self._store().set_password(OPENAI_CREDENTIAL_TARGET, cleaned)

    def get_api_key(self) -> str | None:
        try:
            value = self._store().get_password(OPENAI_CREDENTIAL_TARGET)
        except CredentialUnavailableError:
            return None
        return value if value else None

    def delete_api_key(self) -> None:
        self._store().delete_password(OPENAI_CREDENTIAL_TARGET)

    def _store(self) -> CredentialStore:
        if self.credential_store is None:
            self.credential_store = default_credential_store()
        return self.credential_store

    def _get_setting(self, key: str) -> str | None:
        if self.db is not None:
            row = self.db.get(ProviderSetting, key)
            return row.value if row else None
        with SessionLocal() as db:
            row = db.get(ProviderSetting, key)
            return row.value if row else None

    def _set_setting(self, key: str, value: str) -> None:
        def write(db: Session) -> None:
            row = db.get(ProviderSetting, key)
            if row is None:
                row = ProviderSetting(key=key, value=value)
                db.add(row)
            else:
                row.value = value
                row.updated_at = datetime.now(UTC)
            db.commit()

        if self.db is not None:
            write(self.db)
            return
        with SessionLocal() as db:
            write(db)
