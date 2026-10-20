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
