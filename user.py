import os
from enum import Enum
from datetime import datetime, timezone
from uuid import UUID, uuid4
import secrets

import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import EmailStr, field_validator
from pwdlib import PasswordHash
from sqlalchemy import String
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Field, Session, select

from auth import create_access_token, decode_access_token
from database import SessionDep, engine

bearer_scheme = HTTPBearer()

router = APIRouter()

class Role(str, Enum):
    admin = "admin"
    user = "user"

#3 minumum so the names are meaningful, it prevents one user from hoarding the names with one and two letters and then selling the accounts for their rarity.
#It enables short names like "Bob" and "Eve" to exist while it prevents the mentioned problems.
MIN_USERNAME_LENGTH = 3

#30 maximum prevents users from entering really long names that would use a lot of storage.
#Having maximum length for a name also helps readabily since names that are too long may be uncomftorable to read
MAX_USERNAME_LENGTH = 30

class UserBase(SQLModel):
    username: str = Field(min_length= MIN_USERNAME_LENGTH, max_length= MAX_USERNAME_LENGTH, unique=True, index=True)
    email: EmailStr = Field(sa_type=String, unique=True, index=True)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()

# NIST SP 800-63B-4 (3.1.1.2): 15 minimum when the password is the only factor.
MIN_PASSWORD_LENGTH = 15

# Bounds input so huge payloads can't be used to waste CPU during hashing.
# Still well above NIST's recommended minimum of 64 allowed characters,
# so passphrases and password-manager passwords fit.
MAX_PASSWORD_LENGTH = 128

class Register(UserBase):
    password: str = Field(min_length= MIN_PASSWORD_LENGTH, max_length= MAX_PASSWORD_LENGTH)

class Login(SQLModel):
    username: str
    password: str

class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"

class UserPublic(UserBase):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    role: Role= Field(default=Role.user)
    created_at: datetime= Field(default_factory=lambda: datetime.now(timezone.utc))

class UserModel(UserPublic, table=True):
    password_hash: str

class UserUpdate(SQLModel):
    username: str | None = Field(default=None, min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH)
    email: EmailStr | None = None
    password: str | None= Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str | None) -> str | None:
        return v.lower() if v else v

password_hasher: PasswordHash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_hasher.verify(plain_password, password_hash)

# Dummy hash used to equalize timing in login: for a non-existent user we still
# run the expensive password check, so response time doesn't reveal which accounts exist.
# (User enumiration via timing attack)
DUMMY_HASH = hash_password("dummy-password")

# Creates the first admin at startup (call it from the lifespan in main.py).
# The password comes from the ADMIN_PASSWORD environment variable.
def seed_admin() -> None:
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return
    with Session(engine) as session:
        if session.exec(select(UserModel).where(UserModel.role == Role.admin)).first():
            return
        session.add(UserModel(
            username="admin",
            email="admin@example.com",
            role=Role.admin,
            password_hash=hash_password(password),
        ))
        session.commit()

def get_current_user(
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserModel:
    try:
        user_id = UUID(decode_access_token(credentials.credentials))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user

def require_admin(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    if current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not allowed")
    return current_user

def ensure_self_or_admin(current_user: UserModel, user_id: UUID) -> None:
    if current_user.id != user_id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not allowed")

@router.post("/users/", status_code=201)
def register(data: Register, session: SessionDep) -> UserPublic:
    if session.exec(select(UserModel).where(UserModel.username == data.username)).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if session.exec(select(UserModel).where(UserModel.email == data.email)).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = UserModel(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )

    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email already taken")
    session.refresh(user)
    return user

@router.post("/login")
def login(data: Login, session: SessionDep) -> Token:
    user = session.exec(select(UserModel).where(UserModel.username == data.username)).first()

    hash_to_check = user.password_hash if user else DUMMY_HASH
    password_ok = verify_password(data.password, hash_to_check)

    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    return Token(access_token=create_access_token(str(user.id)))

@router.get("/users/", dependencies=[Depends(require_admin)])
def list_users(session: SessionDep) -> list[UserPublic]:
    return session.exec(select(UserModel)).all()

@router.get("/users/me")
def read_me(current_user: UserModel = Depends(get_current_user)) -> UserPublic:
    return current_user

@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    session: SessionDep,
    current_user: UserModel = Depends(get_current_user),
) -> UserPublic:
    try:
        parsed_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    ensure_self_or_admin(current_user, parsed_id)

    user = session.get(UserModel, parsed_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/users/{user_id}")
def update_user(user_id: UUID, data: UserUpdate,session: SessionDep, current_user: UserModel = Depends(get_current_user)) -> UserPublic:
    ensure_self_or_admin(current_user, user_id)
    
    user = session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    if "username" in changes:
        taken = session.exec(
            select(UserModel).where(UserModel.username == changes["username"], UserModel.id != user_id)
        ).first()
        if taken:
            raise HTTPException(status_code=409, detail="Username already taken")
    if "email" in changes:
        taken = session.exec(
            select(UserModel).where(UserModel.email == changes["email"], UserModel.id != user_id)
        ).first()
        if taken:
            raise HTTPException(status_code=409, detail="Email already registered")

    if "password" in changes:
        changes["password_hash"] = hash_password(changes.pop("password"))

    user.sqlmodel_update(changes)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email already taken")
    session.refresh(user)
    return user
    
        
@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: UUID,
    session: SessionDep,
    current_user: UserModel = Depends(get_current_user),
) -> None:
    ensure_self_or_admin(current_user, user_id)

    user = session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()

