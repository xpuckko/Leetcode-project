from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from user import require_admin

router = APIRouter()

class LanguageIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    judge0_language_id: int = Field(gt=0)
    is_enabled: bool = True

class Language(LanguageIn):
    id: int

languages_db: dict[int, dict] = {}
next_language_id: int = 1

@router.post("/languages/", status_code=201, dependencies=[Depends(require_admin)])
async def create_language(data: LanguageIn) -> Language:
    global next_language_id

    for lang in languages_db.values():
        if lang["name"].lower() == data.name.lower():
            raise HTTPException(status_code=409, detail="Language name already exists")
        if lang["judge0_language_id"] == data.judge0_language_id:
            raise HTTPException(status_code=409, detail="Judge0 language ID already exists")

    language = Language(
        id = next_language_id,
        **data.model_dump()
    )
    next_language_id += 1
    languages_db[language.id] = language.model_dump() 
    return language

