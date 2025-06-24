import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple
from abc import ABC, abstractmethod
import logging
import json
from passlib.hash import bcrypt
import uuid

logger = logging.getLogger("fastapi_cron.state")

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

class StateBackend(ABC):
    """Abstract base class for state backends."""
    
    @abstractmethod
    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job."""
        pass
    
    @abstractmethod
    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        pass
    
    @abstractmethod
    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        pass
    
    @abstractmethod
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job (running, completed, failed)."""
        pass
    
    @abstractmethod
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        pass

class SQLiteStateBackend(StateBackend):
    """SQLite-based state backend with thread safety."""
    
    def __init__(self, db_path: str = "cron_state.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def _ensure_tables(self, db):
        """Ensure required tables exist."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_state (
                name TEXT PRIMARY KEY,
                last_run TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_status (
                name TEXT PRIMARY KEY,
                status TEXT,
                instance_id TEXT,
                started_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT,
                instance_id TEXT,
                status TEXT,
                started_at TEXT,
                completed_at TEXT,
                duration REAL,
                error_message TEXT,
                parameters TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # New: job_definitions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_definitions (
                name TEXT PRIMARY KEY,
                expr TEXT NOT NULL,
                tags TEXT,
                code TEXT,
                is_async INTEGER DEFAULT 0,
                dependencies TEXT,
                on_success TEXT,
                on_failure TEXT,
                parameters_schema TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job with thread safety."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    """INSERT OR REPLACE INTO job_state (name, last_run, updated_at) 
                       VALUES (?, ?, ?)""",
                    (job_name, timestamp.isoformat(), datetime.now().isoformat())
                )
                await db.commit()

    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT last_run FROM job_state WHERE name=?", (job_name,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT name, last_run FROM job_state ORDER BY name") as cursor:
                return await cursor.fetchall()
    
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                now = datetime.now().isoformat()
                
                if status == "running":
                    await db.execute(
                        """INSERT OR REPLACE INTO job_status 
                           (name, status, instance_id, started_at, updated_at) 
                           VALUES (?, ?, ?, ?, ?)""",
                        (job_name, status, instance_id, now, now)
                    )
                else:
                    await db.execute(
                        """UPDATE job_status 
                           SET status = ?, updated_at = ? 
                           WHERE name = ? AND instance_id = ?""",
                        (status, now, job_name, instance_id)
                    )
                
                await db.commit()
    
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT status, instance_id, started_at, updated_at FROM job_status WHERE name=?", 
                (job_name,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "status": row[0],
                        "instance_id": row[1],
                        "started_at": row[2],
                        "updated_at": row[3]
                    }
                return None
    
    async def log_job_execution(self, job_name: str, instance_id: str, status: str, 
                               started_at: datetime, completed_at: Optional[datetime] = None,
                               duration: Optional[float] = None, error_message: Optional[str] = None,
                               parameters: Optional[dict] = None):
        """Log job execution details, including parameters."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    """INSERT INTO job_execution_log 
                       (job_name, instance_id, status, started_at, completed_at, duration, error_message, parameters)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job_name, instance_id, status, started_at.isoformat(),
                     completed_at.isoformat() if completed_at else None,
                     duration, error_message, json.dumps(parameters) if parameters else None)
                )
                await db.commit()

    # --- Job Definition CRUD ---
    async def create_job(self, name, expr, tags=None, code=None, is_async=False, dependencies=None, on_success=None, on_failure=None, parameters_schema=None):
        tags_json = json.dumps(tags) if tags else None
        dependencies_json = json.dumps(dependencies) if dependencies else None
        on_success_json = json.dumps(on_success) if on_success else None
        on_failure_json = json.dumps(on_failure) if on_failure else None
        parameters_schema_json = json.dumps(parameters_schema) if parameters_schema else None
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                now = datetime.now().isoformat()
                await db.execute(
                    """INSERT INTO job_definitions (name, expr, tags, code, is_async, dependencies, on_success, on_failure, parameters_schema, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, expr, tags_json, code, int(is_async), dependencies_json, on_success_json, on_failure_json, parameters_schema_json, now, now)
                )
                await db.commit()

    async def get_job(self, name):
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT name, expr, tags, code, is_async, dependencies, on_success, on_failure, parameters_schema, created_at, updated_at FROM job_definitions WHERE name=?",
                (name,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "name": row[0],
                        "expr": row[1],
                        "tags": json.loads(row[2]) if row[2] else [],
                        "code": row[3],
                        "is_async": bool(row[4]),
                        "dependencies": json.loads(row[5]) if row[5] else [],
                        "on_success": json.loads(row[6]) if row[6] else [],
                        "on_failure": json.loads(row[7]) if row[7] else [],
                        "parameters_schema": json.loads(row[8]) if row[8] else None,
                        "created_at": row[9],
                        "updated_at": row[10],
                    }
                return None

    async def get_all_job_definitions(self):
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT name, expr, tags, code, is_async, dependencies, on_success, on_failure, parameters_schema, created_at, updated_at FROM job_definitions ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "name": row[0],
                        "expr": row[1],
                        "tags": json.loads(row[2]) if row[2] else [],
                        "code": row[3],
                        "is_async": bool(row[4]),
                        "dependencies": json.loads(row[5]) if row[5] else [],
                        "on_success": json.loads(row[6]) if row[6] else [],
                        "on_failure": json.loads(row[7]) if row[7] else [],
                        "parameters_schema": json.loads(row[8]) if row[8] else None,
                        "created_at": row[9],
                        "updated_at": row[10],
                    }
                    for row in rows
                ]

    async def update_job(self, name, expr=None, tags=None, code=None, is_async=None, dependencies=None, on_success=None, on_failure=None, parameters_schema=None):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                now = datetime.now().isoformat()
                fields = []
                values = []
                if expr is not None:
                    fields.append("expr = ?")
                    values.append(expr)
                if tags is not None:
                    fields.append("tags = ?")
                    values.append(json.dumps(tags))
                if code is not None:
                    fields.append("code = ?")
                    values.append(code)
                if is_async is not None:
                    fields.append("is_async = ?")
                    values.append(int(is_async))
                if dependencies is not None:
                    fields.append("dependencies = ?")
                    values.append(json.dumps(dependencies))
                if on_success is not None:
                    fields.append("on_success = ?")
                    values.append(json.dumps(on_success))
                if on_failure is not None:
                    fields.append("on_failure = ?")
                    values.append(json.dumps(on_failure))
                if parameters_schema is not None:
                    fields.append("parameters_schema = ?")
                    values.append(json.dumps(parameters_schema))
                fields.append("updated_at = ?")
                values.append(now)
                values.append(name)
                sql = f"UPDATE job_definitions SET {', '.join(fields)} WHERE name = ?"
                await db.execute(sql, values)
                await db.commit()

    async def delete_job(self, name):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute("DELETE FROM job_definitions WHERE name = ?", (name,))
                await db.commit()

    async def get_job_logs(self, job_name: str, limit: int = 50):
        """Fetch execution logs for a job, most recent first."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                """
                SELECT status, instance_id, started_at, completed_at, duration, error_message, parameters, created_at
                FROM job_execution_log
                WHERE job_name = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_name, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "status": row[0],
                        "instance_id": row[1],
                        "started_at": row[2],
                        "completed_at": row[3],
                        "duration": row[4],
                        "error_message": row[5],
                        "parameters": json.loads(row[6]) if row[6] else None,
                        "created_at": row[7],
                    }
                    for row in rows
                ]

    # --- User Management ---
    async def create_user(self, username: str, password: str, role: str = 'user'):
        hashed_password = bcrypt.hash(password)
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
                    (username, hashed_password, role)
                )
                await db.commit()

    async def get_user_by_username(self, username: str):
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT id, username, hashed_password, role, created_at FROM users WHERE username = ?",
                (username,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "username": row[1],
                        "hashed_password": row[2],
                        "role": row[3],
                        "created_at": row[4],
                    }
                return None

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT id, username, role, created_at FROM users ORDER BY username"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "username": row[1],
                        "role": row[2],
                        "created_at": row[3],
                    }
                    for row in rows
                ]

    async def update_user_role(self, username: str, new_role: str):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    "UPDATE users SET role = ? WHERE username = ?",
                    (new_role, username)
                )
                await db.commit()

    async def delete_user(self, username: str):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    "DELETE FROM users WHERE username = ?",
                    (username,)
                )
                await db.commit()

class RedisStateBackend(StateBackend):
    """Redis-based state backend for distributed deployments."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job."""
        key = f"cron:job:{job_name}:last_run"
        await self.redis.set(key, timestamp.isoformat())
    
    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        key = f"cron:job:{job_name}:last_run"
        result = await self.redis.get(key)
        return result.decode() if result else None
    
    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        pattern = "cron:job:*:last_run"
        keys = await self.redis.keys(pattern)
        
        jobs = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            job_name = key_str.split(":")[2]  # Extract job name from key
            last_run = await self.redis.get(key)
            last_run_str = last_run.decode() if last_run else None
            jobs.append((job_name, last_run_str))
        
        return sorted(jobs)
    
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job."""
        key = f"cron:job:{job_name}:status"
        status_data = {
            "status": status,
            "instance_id": instance_id,
            "updated_at": datetime.now().isoformat()
        }
        
        if status == "running":
            status_data["started_at"] = datetime.now().isoformat()
        
        await self.redis.hset(key, mapping=status_data)
        
        # Set expiration for status (cleanup old statuses)
        await self.redis.expire(key, 3600)  # 1 hour
    
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        key = f"cron:job:{job_name}:status"
        result = await self.redis.hgetall(key)
        
        if result:
            return {k.decode(): v.decode() for k, v in result.items()}
        return None

class RedisLockManager:
    def __init__(self, redis_url="redis://localhost:6379/0", lock_key="cronapi:leader", ttl=10):
        if not REDIS_AVAILABLE:
            raise ImportError("redis.asyncio is required for RedisLockManager")
        self.redis = redis.from_url(redis_url)
        self.lock_key = lock_key
        self.ttl = ttl  # seconds
        self.instance_id = str(uuid.uuid4())
        self._lock_renew_task = None
        self._is_leader = False

    async def acquire_lock(self):
        # Try to acquire the lock with NX (set if not exists) and PX (expire)
        result = await self.redis.set(self.lock_key, self.instance_id, nx=True, ex=self.ttl)
        if result:
            self._is_leader = True
            if not self._lock_renew_task:
                self._lock_renew_task = asyncio.create_task(self._renew_lock())
            return True
        return False

    async def _renew_lock(self):
        # Periodically renew the lock if still leader
        while self._is_leader:
            await asyncio.sleep(self.ttl / 2)
            val = await self.redis.get(self.lock_key)
            if val and val.decode() == self.instance_id:
                await self.redis.expire(self.lock_key, self.ttl)
            else:
                self._is_leader = False
                break

    async def release_lock(self):
        val = await self.redis.get(self.lock_key)
        if val and val.decode() == self.instance_id:
            await self.redis.delete(self.lock_key)
        self._is_leader = False
        if self._lock_renew_task:
            self._lock_renew_task.cancel()
            self._lock_renew_task = None

    async def is_leader(self):
        val = await self.redis.get(self.lock_key)
        return val and val.decode() == self.instance_id

    async def get_leader_id(self):
        val = await self.redis.get(self.lock_key)
        return val.decode() if val else None
