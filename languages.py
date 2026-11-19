from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Field, select
from pydantic import StringConstraints
from typing import Annotated

from database import SessionDep
from user import require_admin

router = APIRouter()

MIN_LENGTH = 1
SLUG_MAX_LENGTH = 50
NAME_MAX_LENGTH = 100


class CreateLanguage(SQLModel):
    slug: Annotated[
        str,
        StringConstraints(
            pattern=r"^[a-z0-9-]+$",
            min_length=MIN_LENGTH,
            max_length=SLUG_MAX_LENGTH,
        )
    ]
    name: str = Field(
        min_length=MIN_LENGTH,
        max_length=NAME_MAX_LENGTH
    )
    judge0_language_id: int = Field(gt=0)
    is_enabled: bool = True

class Language(CreateLanguage, table=True):
    slug: str = Field(primary_key=True)
    name: str = Field(unique=True, index=True)
    judge0_language_id: int = Field(unique=True, index=True)

class UpdateLanguage(SQLModel):
    name: str | None = Field(default=None, min_length=MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    judge0_language_id: int | None = Field(default=None, gt=0)
    is_enabled: bool | None = None


class PublicLanguage(SQLModel):
    slug: str
    name: str


def ensure_unique(session: SessionDep,name: str | None, judge0_language_id: int | None, exclude_slug: str | None = None) -> None:
    if name is not None:
        query = select(Language).where(func.lower(Language.name)==name.lower())
    if exclude_slug is not None:
        query = query.where(Language.slug != exclude_slug)
    if session.exec(query).first():
        raise HTTPException(status_code=409, detail="Language name already exists")

    if judge0_language_id is not None:
        query = select(Language).where(Language.judge0_language_id == judge0_language_id)
        if exclude_slug is not None:
            query = query.where(Language.slug != exclude_slug)
        if session.exec(query).first():
            raise HTTPException(status_code=409, detail="Judge0 language ID already exists")

def get_enabled_language(session: SessionDep, slug: str) -> Language:
    lang = session.get(Language, slug)
    if lang is None or not lang.is_enabled:
        raise HTTPException(status_code=404, detail="Language not found")
    return lang


@router.get("/languages/")
def list_languages(session: SessionDep) -> list[PublicLanguage]:
    langs = session.exec(select(Language).where(Language.is_enabled == True)).all()
    return [PublicLanguage(slug=l.slug, name=l.name) for l in langs]

@router.get("/languages/{slug}")
def get_language(slug: str, session: SessionDep) -> PublicLanguage:
    lang = get_enabled_language(session, slug)
    return PublicLanguage(slug=lang.slug, name=lang.name)

@router.get("/admin/languages/", dependencies=[Depends(require_admin)])
def admin_list_languages(session: SessionDep) -> list[Language]:
    return session.exec(select(Language)).all()

@router.post("/languages/", status_code=201, dependencies=[Depends(require_admin)])
async def create_language(data: CreateLanguage, session: SessionDep) -> Language:
    if session.get(Language, data.slug):
        raise HTTPException(status_code=409, detail="Language slug already exists")
    ensure_unique(session, data.name, data.judge0_language_id)

    language = Language(**data.model_dump())
    session.add(language)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Language already exists")
    session.refresh(language)
    return language

@router.patch("/languages/{slug}", dependencies=[Depends(require_admin)])
async def update_language(slug: str, data: UpdateLanguage, session: SessionDep) -> Language:
    lang = session.get(Language, slug)
    if lang is None:
        raise HTTPException(status_code=404, detail="Language not found")

    changes = data.model_dump(exclude_none=True)
    ensure_unique(session, changes.get("name"), changes.get("judge0_language_id"), exclude_slug=slug)

    lang.sqlmodel_update(changes)
    session.add(lang)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Language name or Judge0 ID already exists")
    session.refresh(lang)
    return lang

