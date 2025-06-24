from ..scheduler import get_crons
from fastapi import APIRouter, Depends
from ..services import user_service

router = APIRouter()

@router.get("/system/status")
async def get_system_status():
    crons = get_crons()
    jobs = await crons.get_jobs()
    backend = crons.state_backend
    running_count = 0
    failed_count = 0
    completed_count = 0
    for job in jobs:
        status_info = await backend.get_job_status(job['name'])
        if status_info:
            if status_info['status'] == 'running':
                running_count += 1
            elif status_info['status'] == 'failed':
                failed_count += 1
            elif status_info['status'] == 'completed':
                completed_count += 1
    return {
        "instance_id": getattr(crons, "instance_id", None),
        "total_jobs": len(jobs),
        "running_jobs": running_count,
        "failed_jobs": failed_count,
        "completed_jobs": completed_count,
        "backend_type": type(backend).__name__,
        "distributed_locking": hasattr(crons, "leader_lock"),
        "redis_configured": hasattr(crons, "leader_lock") and crons.leader_lock is not None,
    }

@router.get("/system/leader")
async def get_leader_status():
    crons = get_crons()
    leader_id = await crons.get_leader_id()
    am_i_leader = await crons.am_i_leader()
    return {
        "leader_id": leader_id,
        "am_i_leader": am_i_leader,
        "instance_id": getattr(crons, "instance_id", None),
    } 