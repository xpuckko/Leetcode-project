from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import create_db_and_tables
import problems
import user
import languages

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(problems.router)
app.include_router(user.router)
app.include_router(languages.router)