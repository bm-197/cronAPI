import asyncio
from typing import List, Optional
from .state import SQLiteStateBackend, StateBackend, RedisLockManager
import logging
from contextlib import asynccontextmanager
import os

logger = logging.getLogger(__name__)

_global_crons = None

class Crons:
    def __init__(self, app=None, state_backend: Optional[StateBackend] = None):
        global _global_crons
        self.jobs: List = []
        self.state_backend = state_backend or SQLiteStateBackend()
        self.app = app
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._startup_delay = 2.0
        self.leader_lock = None
        self.is_leader = False
        self.instance_id = None
        _global_crons = self
        if app:
            self.init_app(app)

    def init_app(self, app):
        existing_lifespan = getattr(app.router, 'lifespan_context', None)
        @asynccontextmanager
        async def lifespan_with_crons(app):
            await asyncio.sleep(self._startup_delay)
            await self.start_leader_election()
            await self.start()
            try:
                if existing_lifespan:
                    async with existing_lifespan(app):
                        yield
                else:
                    yield
            finally:
                await self.stop()
                await self.stop_leader_election()
        app.router.lifespan_context = lifespan_with_crons

    async def start_leader_election(self):
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.leader_lock = RedisLockManager(redis_url=redis_url)
        acquired = await self.leader_lock.acquire_lock()
        self.is_leader = acquired
        self.instance_id = self.leader_lock.instance_id
        if acquired:
            logger.info(f"This instance ({self.instance_id}) is the leader.")
        else:
            logger.info(f"This instance ({self.instance_id}) is NOT the leader.")

    async def stop_leader_election(self):
        if self.leader_lock:
            await self.leader_lock.release_lock()
            self.is_leader = False
            self.leader_lock = None

    async def load_jobs_from_db(self):
        job_defs = await self.state_backend.get_all_job_definitions()
        self.jobs = []
        for job_def in job_defs:
            local_vars = {}
            code = job_def["code"]
            if code:
                exec(code, {}, local_vars)
                func = None
                for v in local_vars.values():
                    if callable(v):
                        func = v
                        break
                if not func:
                    continue
            else:
                continue
            job = {
                "func": func,
                "expr": job_def["expr"],
                "name": job_def["name"],
                "tags": job_def["tags"]
            }
            self.jobs.append(job)

    async def start(self):
        if self._running:
            return
        self._running = True
        await self.load_jobs_from_db()
        if not self.jobs:
            logger.info("No jobs found, waiting for job registration...")
            for i in range(10):
                await asyncio.sleep(0.5)
                await self.load_jobs_from_db()
                if self.jobs:
                    break
        logger.info(f"Starting cron scheduler with {len(self.jobs)} jobs")
        if not self.jobs:
            logger.warning("No cron jobs registered!")
            return
        if not self.is_leader:
            logger.info("This instance is not the leader. Scheduler will not run jobs.")
            return
        for job in self.jobs:
            logger.info(f"Starting job loop for '{job['name']}' with expression '{job['expr']}'")
            # Job execution logic would go here
            # For REST API, jobs are triggered via endpoints

    async def stop(self):
        if not self._running:
            return
        self._running = False
        logger.info("Stopping cron scheduler")
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def add_job(self, name, expr, tags=None, code=None, is_async=False, dependencies=None, on_success=None, on_failure=None, parameters_schema=None):
        await self.state_backend.create_job(name, expr, tags, code, is_async, dependencies, on_success, on_failure, parameters_schema)
        await self.load_jobs_from_db()

    async def update_job(self, name, expr=None, tags=None, code=None, is_async=None, dependencies=None, on_success=None, on_failure=None, parameters_schema=None):
        await self.state_backend.update_job(name, expr, tags, code, is_async, dependencies, on_success, on_failure, parameters_schema)
        await self.load_jobs_from_db()

    async def remove_job(self, name):
        await self.state_backend.delete_job(name)
        await self.load_jobs_from_db()

    async def get_job(self, name):
        """Get a job by name, loading it from the database if not in memory."""
        # First check if job is already loaded
        for job in self.jobs:
            if job.get('name') == name:
                return job
        
        # If not found, try to load from database
        job_def = await self.state_backend.get_job(name)
        if not job_def:
            return None
        
        # Load the job into memory
        local_vars = {}
        code = job_def["code"]
        if code:
            exec(code, {}, local_vars)
            func = None
            for v in local_vars.values():
                if callable(v):
                    func = v
                    break
            if func:
                job = {
                    "func": func,
                    "expr": job_def["expr"],
                    "name": job_def["name"],
                    "tags": job_def["tags"],
                    "dependencies": job_def.get("dependencies"),
                    "on_success": job_def.get("on_success"),
                    "on_failure": job_def.get("on_failure"),
                    "parameters_schema": job_def.get("parameters_schema")
                }
                self.jobs.append(job)
                return job
        
        return None

    async def get_leader_id(self):
        if self.leader_lock:
            return await self.leader_lock.get_leader_id()
        return None

    async def am_i_leader(self):
        if self.leader_lock:
            return await self.leader_lock.is_leader()
        return False

    async def can_run_job(self, job_def):
        # Check if all dependencies have succeeded since last run
        if not job_def.get('dependencies'):
            return True
        backend = self.state_backend
        last_run = await backend.get_last_run(job_def['name'])
        for dep in job_def['dependencies']:
            dep_status = await backend.get_job_status(dep)
            dep_last_run = await backend.get_last_run(dep)
            if not dep_status or dep_status['status'] != 'completed':
                return False
            if last_run and dep_last_run and dep_last_run < last_run:
                return False
        return True

    async def run_job(self, job_def, params=None):
        # Run the job if dependencies are met
        if not await self.can_run_job(job_def):
            logger.info(f"Job '{job_def['name']}' waiting for dependencies.")
            return
        try:
            if asyncio.iscoroutinefunction(job_def['func']):
                result = await job_def['func'](params) if params else await job_def['func']()
            else:
                result = await asyncio.to_thread(job_def['func'], params) if params else await asyncio.to_thread(job_def['func'])
            logger.info(f"Job '{job_def['name']}' executed successfully.")
            await self.handle_chaining(job_def, success=True)
        except Exception as e:
            logger.error(f"Job '{job_def['name']}' failed: {e}")
            await self.handle_chaining(job_def, success=False)

    async def handle_chaining(self, job_def, success):
        # Trigger chained jobs on success or failure
        next_jobs = job_def.get('on_success') if success else job_def.get('on_failure')
        if next_jobs and isinstance(next_jobs, list):
            for next_job_name in next_jobs:
                if self.jobs:  # Check if jobs list exists and is not empty
                    next_job_def = next((j for j in self.jobs if j['name'] == next_job_name), None)
                    if next_job_def:
                        logger.info(f"Chaining: triggering job '{next_job_name}' after '{job_def['name']}'")
                        await self.run_job(next_job_def)

    async def get_jobs(self):
        # Ensure jobs are loaded from DB
        if not self.jobs:
            await self.load_jobs_from_db()
        return self.jobs

# Convenience function to get the global crons instance
def get_crons() -> Crons:
    """Get the global crons instance, creating one if it doesn't exist."""
    global _global_crons
    if _global_crons is None:
        _global_crons = Crons()
    return _global_crons
