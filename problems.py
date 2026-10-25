from enum import Enum
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

problems_db: dict[int, dict] = {}


class Problem(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    time_limit_sec: float = Field(gt=0, le=60)
    memory_limit_kb: int = Field(gt=0)
    is_published: bool = False
    created_at: datetime | None = None
    difficulty: Difficulty

next_problem_id = 1

@router.get("/problems/")
async def list_problems(difficulty: Difficulty | None = None) -> list[Problem]:
    problems = list(problems_db.values())
    if difficulty is not None:
        problems = [p for p in problems if p["difficulty"] == difficulty]
    return problems

@router.get("/problems/{problem_id}")
async def get_problem(problem_id: int) -> Problem:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problems_db[problem_id]
    
@router.post("/problems/", status_code=201)
async def create_problem(problem: Problem) -> Problem:
    global next_problem_id
    problem.id = next_problem_id
    problem.created_at = datetime.now(timezone.utc)
    problems_db[next_problem_id] = problem.model_dump()
    next_problem_id += 1
    return problem

@router.delete("/problems/{problem_id}", status_code=204)
async def del_problem(problem_id: int) -> None:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    del problems_db[problem_id]

@router.put("/problems/{problem_id}")
async def update_problem(problem_id: int, problem: Problem) -> Problem:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    problem.id = problem_id
    problem.created_at = problems_db[problem_id]["created_at"]
    problems_db[problem_id] = problem.model_dump()
    return problem