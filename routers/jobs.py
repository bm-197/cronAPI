from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Optional
from datetime import datetime
import asyncio
from ..scheduler import get_crons
from ..schemas import JobCreateRequest, JobUpdateRequest
from .auth import admin_required
from ..services import job_service
from ..services import user_service
from ..utils.jsonschema import validate_json_schema
from ..utils.errors import error_response
from ..utils.time import humanize_timedelta

router = APIRouter()

@router.post("/jobs", dependencies=[Depends(admin_required)])
async def create_job(req: JobCreateRequest):
    try:
        crons = get_crons()
        if await crons.state_backend.get_job(req.name):
            raise HTTPException(status_code=409, detail=f"Job '{req.name}' already exists")
        await crons.add_job(req.name, req.expr, req.tags, req.code, req.is_async, req.dependencies, req.on_success, req.on_failure, req.parameters_schema)
        return {"status": "success", "message": f"Job '{req.name}' created"}
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating job: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")

@router.put("/jobs/{name}", dependencies=[Depends(admin_required)])
async def update_job(name: str, req: JobUpdateRequest):
    crons = get_crons()
    if not await crons.state_backend.get_job(name):
        raise error_response(Exception(f"Job '{name}' not found"))
    await crons.update_job(name, req.expr, req.tags, req.code, req.is_async, req.dependencies, req.on_success, req.on_failure, req.parameters_schema)
    return {"status": "success", "message": f"Job '{name}' updated"}

@router.delete("/jobs/{name}", dependencies=[Depends(admin_required)])
async def delete_job(name: str):
    crons = get_crons()
    if not await crons.state_backend.get_job(name):
        raise error_response(Exception(f"Job '{name}' not found"))
    await crons.remove_job(name)
    return {"status": "success", "message": f"Job '{name}' deleted"}

@router.get("/jobs")
async def list_job_definitions():
    crons = get_crons()
    jobs = await crons.state_backend.get_all_job_definitions()
    return jobs

@router.get("/jobs/{name}/logs")
async def get_job_logs(name: str, limit: int = 50):
    crons = get_crons()
    if not await crons.state_backend.get_job(name):
        raise error_response(Exception(f"Job '{name}' not found"))
    logs = await crons.state_backend.get_job_logs(name, limit)
    # Optionally, format durations
    for log in logs:
        if log.get('duration') is not None:
            log['duration_human'] = humanize_timedelta(datetime.timedelta(seconds=log['duration']))
    return logs

@router.get("/jobs/{job_name}")
async def get_cron_job(job_name: str):
    crons = get_crons()
    job = await crons.get_job(job_name)
    if not job:
        raise error_response(Exception(f"Job '{job_name}' not found"))
    backend = crons.state_backend
    last_run = await backend.get_last_run(job['name'])
    status_info = await backend.get_job_status(job['name'])
    return {
        "name": job['name'],
        "expr": job['expr'],
        "tags": job['tags'],
        "last_run": last_run,
        "status": status_info,
        "dependencies": job.get('dependencies', []),
        "on_success": job.get('on_success', []),
        "on_failure": job.get('on_failure', [])
    }

@router.post("/jobs/{job_name}/run")
async def run_job(job_name: str, force: bool = False, parameters: Optional[dict] = Body(None)):
    try:
        crons = get_crons()
        job = await crons.get_job(job_name)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
        
        # Get the database job definition for validation
        job_def = await crons.state_backend.get_job(job_name)
        if not job_def:
            raise HTTPException(status_code=404, detail=f"Job definition '{job_name}' not found in database")
        
        # Validate parameters before running the job
        if job_def.get("parameters_schema"):
            try:
                validate_json_schema(parameters or {}, job_def["parameters_schema"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
        
        # Combine the job data (func from scheduler, other fields from database)
        combined_job_def = {**job_def, **job}
        result = await job_service.run_job(combined_job_def, parameters)
        return result
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in run_job: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to run job: {str(e)}") 