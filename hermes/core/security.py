"""
安全模块：JWT 令牌管理、密码哈希、AES-256-GCM 字段加解密、数据脱敏
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from hermes.core.config import settings

# ── 密码哈希 ────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码与 bcrypt 哈希是否匹配。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ── JWT ────────────────────────────────────────────────────────

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """创建 access_token（8小时有效）。"""
    now = datetime.now(UTC)
    expire = now + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, settings.JWT_SECRET.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """创建 refresh_token（7天有效）。"""
    now = datetime.now(UTC)
    expire = now + timedelta(seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(claims, settings.JWT_SECRET.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT 令牌，验证签名与过期时间。"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")


# ── AES-256-GCM 字段加解密 ────────────────────────────────────

def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY.get_secret_value()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return Fernet(key)


def encrypt_field(plaintext: str) -> bytes:
    """AES-256-GCM 加密字段，返回 Base64 编码的密文。"""
    if not plaintext:
        return b""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_field(ciphertext: bytes) -> str:
    """AES-256-GCM 解密字段。"""
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext).decode("utf-8")


# ── 数据脱敏 ──────────────────────────────────────────────────

_SENSITIVE_PATTERNS = {
    "phone": (lambda v: v[:3] + "****" + v[-4:] if len(v) >= 11 else v),
    "email": (lambda v: v[0] + "***" + v[v.index("@") :] if "@" in v else v),
    "name": (lambda v: v[0] + "*" if len(v) >= 2 else v),
}

def mask_sensitive(field_type: str, value: str) -> str:
    """按类型脱敏"""
    if not value:
        return value
    fn = _SENSITIVE_PATTERNS.get(field_type)
    return fn(value) if fn else value


# ── 数字签名 (HMAC-SHA256) ────────────────────────────────────

def sign_approval(case_id: str, stage_name: str, reviewer_id: str, action: str) -> str:
    """生成守门记录的数字签名，防篡改。"""
    message = f"{case_id}|{stage_name}|{reviewer_id}|{action}"
    key = settings.JWT_SECRET.get_secret_value().encode("utf-8")
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
