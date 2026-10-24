<<<<<<< HEAD
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

problems_db: list[dict] = []

class Problem(BaseModel):
    title: str
    description: str
    difficulty: Difficulty

@app.get("/problems/")
async def list_problems():
    return problems_db

@app.get("/problems/{problem_id}")
async def get_problem(problem_id: int):
    if problem_id < 0 or problem_id >= len(problems_db):
        raise HTTPException(status_code=404, detail="Problem not found")
    return problems_db[problem_id]

@app.post("/problems/")
async def create_problem(problem: Problem):
    problems_db.append(problem.model_dump())
    return problem
=======
from enum import Enum
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()

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

@app.get("/problems/")
async def list_problems(difficulty: Difficulty | None = None) -> list[dict]:
    problems = list(problems_db.values())
    if difficulty is not None:
        problems = [p for p in problems if p["difficulty"] == difficulty]
    return problems

@app.get("/problems/{problem_id}")
async def get_problem(problem_id: int) -> dict:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problems_db[problem_id]
    
@app.post("/problems/", status_code=201)
async def create_problem(problem: Problem) -> Problem:
    global next_id
    problem.id = next_id
    problem.created_at = datetime.now(timezone.utc)
    problems_db[next_problem_id] = problem.model_dump()
    next_problem_id += 1
    return problem

@app.delete("/problems/{problem_id}", status_code=204)
async def del_problem(problem_id: int) -> None:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    del problems_db[problem_id]

@app.put("/problems/{problem_id}")
async def update_problem(problem_id: int, problem: Problem) -> Problem:
    if problem_id not in problems_db:
        raise HTTPException(status_code=404, detail="Problem not found")
    problem.id = problem_id
    problem.created_at = problems_db[problem_id]["created_at"]
    problems_db[problem_id] = problem.model_dump()
    return problem
>>>>>>> master
