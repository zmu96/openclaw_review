"""
bot/key_store.py — Discord 사용자 Anthropic API 키 암호화 저장소

Fernet 대칭 암호화로 사용자별 API 키를 인메모리에 저장합니다.
FERNET_KEY 환경변수가 없으면 런타임에 임시 키를 생성합니다 (재시작 시 초기화).
"""

import os
from cryptography.fernet import Fernet


def _init_fernet() -> Fernet:
    raw = os.getenv("FERNET_KEY")
    if raw:
        return Fernet(raw.encode())
    key = Fernet.generate_key()
    print(
        f"[KeyStore] FERNET_KEY 미설정 — 임시 키 사용 (재시작 시 모든 사용자 키 초기화).\n"
        f"[KeyStore] 영구 저장을 원하면 환경변수에 추가: FERNET_KEY={key.decode()}"
    )
    return Fernet(key)


_fernet = _init_fernet()
_store: dict[int, bytes] = {}  # user_id → encrypted api key


def set_key(user_id: int, api_key: str) -> None:
    _store[user_id] = _fernet.encrypt(api_key.encode())


def get_key(user_id: int) -> str | None:
    encrypted = _store.get(user_id)
    if encrypted is None:
        return None
    return _fernet.decrypt(encrypted).decode()


def has_key(user_id: int) -> bool:
    return user_id in _store


def delete_key(user_id: int) -> None:
    _store.pop(user_id, None)
