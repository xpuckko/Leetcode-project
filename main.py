from fastapi import FastAPI

import problems
import user
import languages

app = FastAPI()
app.include_router(problems.router)
app.include_router(user.router)
app.include_router(languages.router)