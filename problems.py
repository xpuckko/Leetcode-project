from enum import Enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import SQLModel, Field, select

from database import SessionDep
from user import require_admin, get_current_user, Role

router = APIRouter()

class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

class ProblemIn(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    description: str
    time_limit_sec: float = Field(gt=0, le=60)
    memory_limit_kb: int = Field(gt=0)
    is_visible: bool = False
    difficulty: Difficulty

class Problem(ProblemIn, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

@router.get("/problems/")
def list_problems(
    session: SessionDep,
    difficulty: Difficulty | None = None,
    current_user: dict = Depends(get_current_user),
) -> list[Problem]:
    query = select(Problem)
    if current_user["role"] != Role.admin:
        query = query.where(Problem.is_visible == True)
    if difficulty is not None:
        query = query.where(Problem.difficulty == difficulty)
    return session.exec(query).all()

@router.get("/problems/{problem_id}")
def get_problem(
    problem_id: UUID,
    session: SessionDep,
    current_user: dict = Depends(get_current_user),
) -> Problem:
    problem = session.get(Problem, problem_id)
    if problem is None or (not problem.is_visible and current_user["role"] != Role.admin):
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem
    
@router.post("/problems/", status_code=201, dependencies=[Depends(require_admin)])
def create_problem(data: ProblemIn, session: SessionDep) -> Problem:
    problem = Problem.model_validate(data)
    session.add(problem)
    session.commit()
    session.refresh(problem)
    return problem

@router.delete("/problems/{problem_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_problem(problem_id: UUID, session: SessionDep) -> None:
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    session.delete(problem)
    session.commit()

@router.put("/problems/{problem_id}", dependencies=[Depends(require_admin)])
def update_problem(problem_id: UUID, data: ProblemIn, session: SessionDep) -> Problem:
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    problem.sqlmodel_update(data.model_dump())
    session.add(problem)
    session.commit()
    session.refresh(problem)
    return problem

