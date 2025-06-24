import os
from fastapi import FastAPI
from .routers import auth, jobs, system
from .scheduler import Crons
from .services.scheduler_service import SchedulerService
from .utils.logging import setup_json_logging

setup_json_logging()

# Ensure data directory exists
data_dir = "/app/data"
os.makedirs(data_dir, exist_ok=True)

app = FastAPI(title="CronAPI - Modular Job Scheduler")

# Initialize scheduler with persistent database
from .state import SQLiteStateBackend
db_path = os.path.join(data_dir, "cron_state.db")
crons = Crons(state_backend=SQLiteStateBackend(db_path))
scheduler_service = SchedulerService(crons)

# Include routers
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(system.router)

@app.on_event("startup")
async def startup_event():
    await scheduler_service.start()

@app.on_event("shutdown")
async def shutdown_event():
    await scheduler_service.stop() 