from fastapi import FastAPI

import problems
import user

app = FastAPI()
app.include_router(problems.router)
app.include_router(user.router)