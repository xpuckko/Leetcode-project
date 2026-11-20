from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import SQLModel, Field, select

from database import SessionDep
from user import require_admin, get_current_user, UserModel, Role
from problems import Problem

router = APIRouter()

# Bounds test case size so huge payloads can't be used to fill the database.
MAX_TEST_CASE_LENGTH = 100_000


class TestCaseIn(SQLModel):
    input: str = Field(max_length=MAX_TEST_CASE_LENGTH)
    expected_output: str = Field(max_length=MAX_TEST_CASE_LENGTH)
    # Visible test cases are shown to users as examples, hidden ones are only used for judging.
    is_visible: bool = False


class TestCase(TestCaseIn, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    problem_id: UUID = Field(foreign_key="problem.id", index=True, ondelete="CASCADE")


class UpdateTestCase(SQLModel):
    input: str | None = Field(default=None, max_length=MAX_TEST_CASE_LENGTH)
    expected_output: str | None = Field(default=None, max_length=MAX_TEST_CASE_LENGTH)
    is_visible: bool | None = None


class PublicTestCase(SQLModel):
    id: UUID
    input: str
    expected_output: str


def get_problem_or_404(session: SessionDep, problem_id: UUID, current_user: UserModel) -> Problem:
    problem = session.get(Problem, problem_id)
    if problem is None or (not problem.is_visible and current_user.role != Role.admin):
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


def get_test_case_or_404(session: SessionDep, problem_id: UUID, test_case_id: UUID) -> TestCase:
    test_case = session.get(TestCase, test_case_id)
    if test_case is None or test_case.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="Test case not found")
    return test_case


@router.get("/problems/{problem_id}/test-cases/")
def list_test_cases(
    problem_id: UUID,
    session: SessionDep,
    current_user: UserModel = Depends(get_current_user),
) -> list[PublicTestCase]:
    get_problem_or_404(session, problem_id, current_user)
    query = select(TestCase).where(TestCase.problem_id == problem_id, TestCase.is_visible == True)
    return session.exec(query).all()


@router.get("/admin/problems/{problem_id}/test-cases/", dependencies=[Depends(require_admin)])
def admin_list_test_cases(problem_id: UUID, session: SessionDep) -> list[TestCase]:
    if session.get(Problem, problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return session.exec(select(TestCase).where(TestCase.problem_id == problem_id)).all()


@router.get("/problems/{problem_id}/test-cases/{test_case_id}", dependencies=[Depends(require_admin)])
def get_test_case(problem_id: UUID, test_case_id: UUID, session: SessionDep) -> TestCase:
    return get_test_case_or_404(session, problem_id, test_case_id)


@router.post("/problems/{problem_id}/test-cases/", status_code=201, dependencies=[Depends(require_admin)])
def create_test_case(problem_id: UUID, data: TestCaseIn, session: SessionDep) -> TestCase:
    if session.get(Problem, problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    test_case = TestCase(**data.model_dump(), problem_id=problem_id)
    session.add(test_case)
    session.commit()
    session.refresh(test_case)
    return test_case


@router.patch("/problems/{problem_id}/test-cases/{test_case_id}", dependencies=[Depends(require_admin)])
def update_test_case(problem_id: UUID, test_case_id: UUID, data: UpdateTestCase, session: SessionDep) -> TestCase:
    test_case = get_test_case_or_404(session, problem_id, test_case_id)

    test_case.sqlmodel_update(data.model_dump(exclude_none=True))
    session.add(test_case)
    session.commit()
    session.refresh(test_case)
    return test_case


@router.delete("/problems/{problem_id}/test-cases/{test_case_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_test_case(problem_id: UUID, test_case_id: UUID, session: SessionDep) -> None:
    test_case = get_test_case_or_404(session, problem_id, test_case_id)
    session.delete(test_case)
    session.commit()