from enum import Enum
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, field_validator
from pwdlib import PasswordHash
from uuid import UUID, uuid4

from auth import create_access_token, decode_access_token

# TODO: create the initial admin user when switching to a SQL database
# (seed script or migration, password from ADMIN_PASSWORD env var)

bearer_scheme = HTTPBearer()

router = APIRouter()

users_db: dict[UUID, dict] = {}

class Role(str, Enum):
    admin = "admin"
    user = "user"

#3 minumum so the names are meaningful, it prevents one user from hoarding the names with one and two letters and then selling the accounts for their rarity.
#It enables short names like "Bob" and "Eve" to exist while it prevents the mentioned problems.
MIN_USERNAME_LENGTH = 3

#30 maximum prevents users from entering really long names that would use a lot of storage.
#Having maximum length for a name also helps readabily since names that are too long may be uncomftorable to read
MAX_USERNAME_LENGTH = 20

class UserBase(BaseModel):
    username: str = Field(min_length= MIN_USERNAME_LENGTH, max_length= MAX_USERNAME_LENGTH)
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()

# NIST SP 800-63B-4 (3.1.1.2): 15 minimum when the password is the only factor.
MIN_PASSWORD_LENGTH = 8

# Bounds input so huge payloads can't be used to waste CPU during hashing.
# Still well above NIST's recommended minimum of 64 allowed characters,
# so passphrases and password-manager passwords fit.
MAX_PASSWORD_LENGTH = 128

class Register(UserBase):
    password: str = Field(min_length= MIN_PASSWORD_LENGTH, max_length= MAX_PASSWORD_LENGTH)

class Login(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserPublic(UserBase):
    id: UUID
    role: Role
    created_at: datetime

class UserModel(UserPublic):
    password_hash: str

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=18)
    email: EmailStr | None = None
    password: str | None= Field(default=None, min_length=8)

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

@router.post("/users/", status_code=201)
async def register(data: Register) -> UserPublic:

    for u in users_db.values():
        if u["username"] == data.username:
            raise HTTPException(status_code=409, detail="Username already taken")
        if u["email"] == data.email:
            raise HTTPException(status_code=409, detail="Email already registered")

    user = UserModel(
        id=uuid4(),
        username=data.username,
        email=data.email,
        role=Role.user,
        created_at=datetime.now(timezone.utc),
        password_hash=hash_password(data.password),
    )

    users_db[user.id] = user.model_dump()
    return user

@router.post("/login")
async def login(data: Login) -> Token:
    user = next((u for u in users_db.values() if u["username"] == data.username), None)

    hash_to_check = user["password_hash"] if user else DUMMY_HASH
    password_ok = verify_password(data.password, hash_to_check)

    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    return Token(access_token=create_access_token(str(user["id"])))

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> dict:
    try:
        user_id = UUID(decode_access_token(credentials.credentials))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = users_db.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != Role.admin:
        raise HTTPException(status_code=403, detail="Not allowed")
    return current_user

def ensure_self_or_admin(current_user: dict, user_id: UUID) -> None:
    if current_user["id"] != user_id and current_user["role"] != Role.admin:
        raise HTTPException(status_code=403, detail="Not allowed")

@router.get("/users/", dependencies=[Depends(require_admin)])
async def list_users() -> list[UserPublic]:
    return list(users_db.values())

@router.get("/users/me")
async def read_me(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return current_user

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
) -> UserPublic:
    try:
        parsed_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")
    
    ensure_self_or_admin(current_user, user_id)

    user = users_db.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic.model_validate(user)

@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, data: UserUpdate, current_user: dict = Depends(get_current_user)) -> UserPublic:
    ensure_self_or_admin(current_user, user_id)
    
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    
    for other_id, u in users_db.items():
        if other_id == user_id:
            continue
        elif "username" in changes and u["username"] == changes["username"]:
            raise HTTPException(status_code=409, detail="Username already taken")
        elif "email" in changes and u["email"] == changes["email"]:
            raise HTTPException(status_code=409, detail="Email already registered")

    if "password" in changes:
        changes["password_hash"] = hash_password(changes.pop("password"))

    users_db[user_id].update(changes)
    return users_db[user_id]
        
@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, current_user: dict= Depends(get_current_user)) -> None:
    ensure_self_or_admin(current_user, user_id)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    del users_db[user_id]

