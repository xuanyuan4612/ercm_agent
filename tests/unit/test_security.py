"""测试安全模块"""

import os
import base64

from hermes.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


def test_hash_and_verify_password():
    """验证密码哈希与校验"""
    password = "MySecurePass123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword", hashed)


def test_jwt_token_roundtrip():
    """验证 JWT 令牌创建与解码"""
    os.environ["JWT_SECRET"] = "test-jwt-secret-for-unit-tests!!"

    token = create_access_token("testuser", {"role": "ecovacs"})
    assert token is not None
    assert len(token) > 20

    payload = decode_token(token)
    assert payload["sub"] == "testuser"
    assert payload["role"] == "ecovacs"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_jwt_decode_invalid_token():
    """验证无效 token 被拒绝"""
    os.environ["JWT_SECRET"] = "test-jwt-secret-for-unit-tests!!"
    try:
        decode_token("invalid.token.here")
        assert False, "Should have raised"
    except ValueError:
        pass  # expected


def test_encryption_roundtrip():
    """验证 AES-256-GCM 加密解密"""
    # Generate a random 32-byte key for testing
    import base64
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    os.environ["ENCRYPTION_KEY"] = key.decode()

    from hermes.core.security import encrypt_field, decrypt_field
    plaintext = "张三"
    ciphertext = encrypt_field(plaintext)
    assert ciphertext != plaintext.encode("utf-8")
    decrypted = decrypt_field(ciphertext)
    assert decrypted == plaintext
