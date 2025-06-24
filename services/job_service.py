import asyncio
import jsonschema
import inspect
from datetime import datetime
from ..scheduler import get_crons

async def can_run_job(job_def, backend):
    # Check if all dependencies have succeeded since last run
    dependencies = job_def.get('dependencies')
    if not dependencies or not isinstance(dependencies, list):
        return True
    last_run = await backend.get_last_run(job_def['name'])
    for dep in dependencies:
        dep_status = await backend.get_job_status(dep)
        dep_last_run = await backend.get_last_run(dep)
        if not dep_status or dep_status['status'] != 'completed':
            return False
        if last_run and dep_last_run and dep_last_run < last_run:
            return False
    return True

async def validate_parameters(parameters, schema):
    if schema:
        jsonschema.validate(instance=parameters or {}, schema=schema)

async def handle_chaining(job_def, jobs, success, run_job_func):
    # Trigger chained jobs on success or failure
    next_jobs = job_def.get('on_success') if success else job_def.get('on_failure')
    if next_jobs and isinstance(next_jobs, list):
        for next_job_name in next_jobs:
            next_job_def = next((j for j in jobs if j['name'] == next_job_name), None)
            if next_job_def:
                await run_job_func(next_job_def)

async def run_job(job_def, parameters=None, backend=None, run_job_func=None):
    # Run the job if dependencies are met
    if backend is None:
        crons = get_crons()
        backend = crons.state_backend
    if not await can_run_job(job_def, backend):
        return {"status": "waiting", "message": f"Job '{job_def['name']}' waiting for dependencies."}
    
    # Check if func exists and is callable
    if 'func' not in job_def or job_def['func'] is None:
        return {"status": "error", "error": f"Job '{job_def['name']}' has no executable function"}
    
    if not callable(job_def['func']):
        return {"status": "error", "error": f"Job '{job_def['name']}' function is not callable"}
    
    try:
        # Check if the function accepts parameters
        sig = inspect.signature(job_def['func'])
        has_params = len(sig.parameters) > 0
        
        if asyncio.iscoroutinefunction(job_def['func']):
            if has_params:
                result = await job_def['func'](parameters or {})
            else:
                result = await job_def['func']()
        else:
            if has_params:
                result = await asyncio.to_thread(job_def['func'], parameters or {})
            else:
                result = await asyncio.to_thread(job_def['func'])
        
        await handle_chaining(job_def, [], True, run_job_func or run_job)
        return {"status": "success", "result": result}
    except Exception as e:
        await handle_chaining(job_def, [], False, run_job_func or run_job)
        return {"status": "failed", "error": str(e)} 