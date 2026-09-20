"""Endpoints d'authentification JWT."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orbit.api.deps import get_current_user, get_db
from orbit.config import settings
from orbit.db.models import User, Client

router = APIRouter(prefix="/auth", tags=["auth"])

# ── bcrypt utilisé directement (contourne l'incompatibilité passlib 1.7 / bcrypt 4.x)
# bcrypt tronque à 72 bytes — on le fait explicitement pour être déterministe.
_MAX_PW_BYTES = 72


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_bytes(password: str) -> bytes:
    """Encode et tronque le mot de passe à 72 bytes (limite bcrypt)."""
    return password.encode("utf-8")[:_MAX_PW_BYTES]


def _hash(password: str) -> str:
    """Hash un mot de passe avec bcrypt (work factor 12)."""
    hashed = _bcrypt.hashpw(_to_bytes(password), _bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def _verify(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    try:
        return _bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> UserOut:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    user = User(email=body.email, hashed_password=_hash(body.password))
    db.add(user)
    await db.flush()  # pour avoir user.id
    client = Client(user_id=user.id, name=body.email)
    db.add(client)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not _verify(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return TokenResponse(access_token=_create_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=current_user.id, email=current_user.email)