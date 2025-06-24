from ..scheduler import get_crons
from fastapi import APIRouter, Depends, HTTPException
from ..services import user_service
import aiosqlite
import redis.asyncio as redis
import os

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint that verifies core system components."""
    try:
        # Get crons instance
        crons = get_crons()
        
        # Check database connectivity
        db_path = os.getenv("DATABASE_PATH", "cron_state.db")
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
        
        # Check Redis if configured
        if hasattr(crons, "leader_lock") and crons.leader_lock:
            redis_client = crons.leader_lock._redis
            await redis_client.ping()
            
        return {
            "status": "healthy",
            "database": "connected",
            "redis": "connected" if hasattr(crons, "leader_lock") and crons.leader_lock else "not_configured"
        }
    except aiosqlite.Error as e:
        raise HTTPException(status_code=503, detail=f"Database health check failed: {str(e)}")
    except redis.RedisError as e:
        raise HTTPException(status_code=503, detail=f"Redis health check failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

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