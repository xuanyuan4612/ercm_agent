"""测试安全模块"""

import base64
import os

import pytest
from cryptography.fernet import Fernet

from hermes.core.config import Settings, settings
from hermes.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_field,
    decode_token,
    encrypt_field,
    hash_password,
    mask_sensitive,
    sign_approval,
    verify_password,
)


def _build_test_settings(**overrides) -> Settings:
    """构建用于测试的 Settings 实例。"""
    defaults = {
        "DB_PASSWORD": "test",
        "REDIS_PASSWORD": "test",
        "RABBITMQ_PASSWORD": "test",
        "MINIO_SECRET_KEY": "test",
        "LLM_API_KEY": "test",
        "LLM_BACKUP_API_KEY": "test",
        "EMBEDDING_API_KEY": "test",
        "JWT_SECRET": "test-jwt-secret-for-unit-tests!!",
        "ENCRYPTION_KEY": "jxmHOG1FgZJDFrKsVgOW0lQioiZ-M9S_VG3DRaRWM_c=",
        "LANGFUSE_SECRET_KEY": "test",
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestPasswordHashing:
    """密码哈希与校验测试"""

    def test_hash_and_verify_success(self):
        password = "MySecurePass123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_verify_wrong_password_fails(self):
        hashed = hash_password("CorrectPassword1!")
        assert not verify_password("WrongPassword1!", hashed)

    def test_hash_is_stable_for_same_input(self):
        """bcrypt 每次生成不同哈希（含随机盐），但验证应一致"""
        password = "TestPass456!"
        h1 = hash_password(password)
        h2 = hash_password(password)
        # bcrypt 每次生成不同的哈希值
        assert h1 != h2
        # 但都能验证通过
        assert verify_password(password, h1)
        assert verify_password(password, h2)


class TestJWT:
    """JWT 令牌管理测试"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        self.test_settings = _build_test_settings()
        monkeypatch.setattr("hermes.core.security.settings", self.test_settings)

    def test_create_and_decode_access_token(self):
        token = create_access_token("testuser", {"role": "ecovacs"})
        assert token is not None
        assert len(token) > 20

        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "ecovacs"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_refresh_token(self):
        token = create_refresh_token("testuser")
        assert token is not None
        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_decode_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("invalid.token.here")

    def test_decode_expired_token_raises(self, monkeypatch):
        # 创建一个立即过期的 token（-1 秒有效期确保一定逾期）
        short_settings = _build_test_settings(ACCESS_TOKEN_EXPIRE_SECONDS=-1)
        monkeypatch.setattr("hermes.core.security.settings", short_settings)
        token = create_access_token("testuser")
        monkeypatch.setattr("hermes.core.security.settings", self.test_settings)

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(token)

    def test_token_with_extra_claims(self):
        token = create_access_token(
            "user1", {"role": "group", "user_id": "uuid-123"}
        )
        payload = decode_token(token)
        assert payload["role"] == "group"
        assert payload["user_id"] == "uuid-123"


class TestEncryption:
    """AES 加解密测试"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        key = Fernet.generate_key()
        test_settings = _build_test_settings(ENCRYPTION_KEY=key.decode())
        monkeypatch.setattr("hermes.core.security.settings", test_settings)

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "张三"
        ciphertext = encrypt_field(plaintext)
        assert ciphertext != plaintext.encode("utf-8")
        decrypted = decrypt_field(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        assert encrypt_field("") == b""

    def test_decrypt_empty_bytes(self):
        assert decrypt_field(b"") == ""

    def test_encrypt_unicode(self):
        text = "中文测试 🎉 émoji"
        ciphertext = encrypt_field(text)
        decrypted = decrypt_field(ciphertext)
        assert decrypted == text

    def test_encrypt_long_text(self):
        text = "A" * 10000
        ciphertext = encrypt_field(text)
        decrypted = decrypt_field(ciphertext)
        assert decrypted == text


class TestMaskSensitive:
    """数据脱敏测试"""

    def test_mask_phone(self):
        assert mask_sensitive("phone", "13812345678") == "138****5678"

    def test_mask_phone_short(self):
        # 少于 11 位不脱敏
        assert mask_sensitive("phone", "1234") == "1234"

    def test_mask_email(self):
        assert mask_sensitive("email", "zhangsan@example.com") == "z***@example.com"

    def test_mask_email_no_at(self):
        assert mask_sensitive("email", "noemail") == "noemail"

    def test_mask_name(self):
        assert mask_sensitive("name", "张三") == "张*"

    def test_mask_name_short(self):
        assert mask_sensitive("name", "张") == "张"

    def test_mask_empty_value(self):
        assert mask_sensitive("phone", "") == ""

    def test_mask_unknown_type(self):
        assert mask_sensitive("unknown", "test") == "test"


class TestSignApproval:
    """数字签名测试"""

    def test_sign_approval_consistent(self):
        s1 = sign_approval("case-1", "intake", "reviewer1", "approved")
        s2 = sign_approval("case-1", "intake", "reviewer1", "approved")
        assert s1 == s2
        assert len(s1) == 64  # SHA256 hex digest

    def test_sign_approval_different_per_case(self):
        s1 = sign_approval("case-1", "intake", "r1", "approved")
        s2 = sign_approval("case-2", "intake", "r1", "approved")
        assert s1 != s2

    def test_sign_approval_different_per_action(self):
        s1 = sign_approval("case-1", "intake", "r1", "approved")
        s2 = sign_approval("case-1", "intake", "r1", "rejected")
        assert s1 != s2

    def test_sign_approval_different_per_stage(self):
        s1 = sign_approval("case-1", "intake", "r1", "approved")
        s2 = sign_approval("case-1", "analysis", "r1", "approved")
        assert s1 != s2
