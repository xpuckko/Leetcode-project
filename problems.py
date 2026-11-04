from enum import Enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from user import require_admin, get_current_user, Role

router = APIRouter()

class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

problems_db: dict[UUID, dict] = {}

class ProblemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str
    time_limit_sec: float = Field(gt=0, le=60)
    memory_limit_kb: int = Field(gt=0)
    is_visible: bool = False
    difficulty: Difficulty

class Problem(ProblemIn):
    id: UUID
    created_at: datetime

@router.get("/problems/")
async def list_problems(
    difficulty: Difficulty | None = None,
    current_user: dict = Depends(get_current_user),
) -> list[Problem]:
    problems = list(problems_db.values())
    if current_user["role"] != Role.admin:
        problems = [p for p in problems if p["is_visible"]]
    if difficulty is not None:
        problems = [p for p in problems if p["difficulty"] == difficulty]
    return problems

@router.get("/problems/{problem_id}")
async def get_problem(
    problem_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> Problem:
    problem = problems_db.get(problem_id)
    if problem is None or (not problem["is_visible"] and current_user["role"] != Role.admin):
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem
    
@router.post("/problems/", status_code=201, dependencies=[Depends(require_admin)])
async def create_problem(data: ProblemIn) -> Problem:
    problem = Problem(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        **data.model_dump()
    )
    problems_db[problem.id] = problem.model_dump()
    return problem

@router.delete("/problems/{problem_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_problem(problem_id: UUID) -> None:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    del problems_db[problem_id]

@router.put("/problems/{problem_id}", dependencies=[Depends(require_admin)])
async def update_problem(problem_id: UUID, data: ProblemIn) -> Problem:
    existing = problems_db.get(problem_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    problem = Problem(
        id=problem_id,
        created_at=existing["created_at"],
        **data.model_dump(),
    )
    problems_db[problem_id] = problem.model_dump()
    return problem
