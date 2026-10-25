from enum import Enum
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, EmailStr
from pwdlib import PasswordHash

router = APIRouter()

users_db: dict[int, dict] = {}
next_user_id: int = 1

class Role(str, Enum):
    admin = "admin"
    user = "user"

class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=18)
    email: EmailStr

class Register(UserBase):
    password: str = Field(min_length=8)

class UserPublic(UserBase):
    id: int
    role: Role
    created_at: datetime

class UserModel(UserPublic):
    password_hash: str

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=18)
    email: EmailStr | None = None
    password: str | None= Field(default=None, min_length=8)

password_hasher: PasswordHash= PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_hasher.verify(plain_password, password_hash)

@router.post("/users/", status_code=201)
async def register(data: Register) -> UserPublic:
    global next_user_id

    for u in users_db.values():
        if u["username"] == data.username:
            raise HTTPException(status_code=409, detail="Username already taken")
        if u["email"] == data.email:
            raise HTTPException(status_code=409, detail="Email already registered")

    user = UserModel(
        id=next_user_id,
        username=data.username,
        email=data.email,
        role=Role.user,
        created_at=datetime.now(timezone.utc),
        password_hash=hash_password(data.password),
    )

    users_db[next_user_id] = user.model_dump()
    next_user_id += 1
    return user

@router.get("/users/")
async def list_users()  -> list[UserPublic]:
    users = list(users_db.values())
    return users

@router.get("/users/{user_id}")
async def get_user(user_id: int) -> UserPublic:
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]

@router.patch("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate) -> UserPublic:
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
async def delete_user(user_id: int) -> None:
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    del users_db[user_id]