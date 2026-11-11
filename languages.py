from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from user import require_admin

router = APIRouter()

MIN_LENGTH = 1
SLUG_MAX_LENGTH = 50
NAME_MAX_LENGTH = 100

class Language(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=MIN_LENGTH, max_length=SLUG_MAX_LENGTH)  # stable id, never changes
    name: str = Field(min_length=MIN_LENGTH, max_length=NAME_MAX_LENGTH)                          # display name, editable
    judge0_language_id: int = Field(gt=0)                                                         # mapping, editable
    is_enabled: bool = True

class UpdateLanguage(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    judge0_language_id: int | None = Field(default=None, gt=0)
    is_enabled: bool | None = None

class PublicLanguage(BaseModel):
    slug: str
    name: str

languages_db: dict[str, Language] = {}

def get_enabled_language(slug: str) -> Language:
    lang = languages_db.get(slug)
    if lang is None or not lang.is_enabled:
        raise HTTPException(status_code = 404, detail="Language not found")
    return lang

def ensure_unique(name: str | None, judge0_language_id: int | None, exclude_slug: str | None = None) -> None:
    for lang in languages_db.values():
        if lang.slug == exclude_slug:
            continue
        if name is not None and lang.name.lower() == name.lower():
            raise HTTPException(status_code=409, detail="Language name already exists")
        if judge0_language_id is not None and lang.judge0_language_id == judge0_language_id:
            raise HTTPException(status_code=409, detail="Judge0 language ID already exists")

@router.get("/languages/")
async def list_languages() -> list[PublicLanguage]:
    return [
        PublicLanguage(slug=l.slug, name=l.name)
        for l in languages_db.values()
        if l.is_enabled
    ]

@router.get("/languages/{slug}")
async def get_langugage(slug: str) -> PublicLanguage:
    lang = get_enabled_language(slug)
    return PublicLanguage(slug=lang.slug, name=lang.name)

@router.get("/admin/languages/", dependencies=[Depends(require_admin)])
async def admin_list_languages() -> list[Language]:
    """Everything, including disabled languages"""
    return list(languages_db.values())

@router.post("/languages/", status_code=201, dependencies=[Depends(require_admin)])
async def create_language(data: Language) -> Language:
    if data.slug in languages_db:
        raise HTTPException(status_code=409, detail="Language slug already exists")
    ensure_unique(data.name, data.judge0_language_id)

    languages_db[data.slug] = data
    return data

@router.patch("/languages/{slug}", dependencies=[Depends(require_admin)])
async def update_language(slug: str, data: UpdateLanguage) -> Language:
    lang = languages_db.get(slug) 
    if lang is None:
        raise HTTPException(status_code=404, detail="Language not found")

    changes = data.model_dump(exclude_none=True)
    ensure_unique(changes.get("name"), changes.get("judge0_language_id"), exclude_slug=slug)

    updated = lang.model_copy(update=changes)
    languages_db[slug] = updated
    return updated

