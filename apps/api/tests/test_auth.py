"""
Tests unitaires de l'authentification (bcrypt direct, JWT, et routes /auth).
"""

import pytest
from jose import jwt

from orbit.api.auth import _create_token, _hash, _verify
from orbit.config import settings


def test_hash_and_verify_success():
    password = "SuperPassword123!"
    hashed = _hash(password)
    assert hashed != password
    assert _verify(password, hashed) is True


def test_verify_fails_with_wrong_password():
    password = "SuperPassword123!"
    hashed = _hash(password)
    assert _verify("WrongPassword", hashed) is False


def test_long_password_truncated_without_error():
    """
    Vérifie le fix de l'incompatibilité passlib 1.7 / bcrypt 4.x :
    Un mot de passe supérieur à 72 octets doit être tronqué sans lever ValueError.
    """
    long_password = "A" * 150  # 150 bytes > 72 bytes limit
    hashed = _hash(long_password)
    assert hashed is not None
    # Doit vérifier avec succès la version tronquée
    assert _verify(long_password, hashed) is True
    # Et ne pas matcher un mot de passe différent
    assert _verify("A" * 10, hashed) is False


def test_create_token_valid_jwt():
    user_id = "user-uuid-1234"
    token = _create_token(user_id)
    assert isinstance(token, str)

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == user_id
    assert "exp" in payload
