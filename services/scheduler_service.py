import os
from ..state import RedisLockManager

class SchedulerService:
    def __init__(self, crons):
        self.crons = crons
        self.leader_lock = None
        self.is_leader = False
        self.instance_id = None

    async def start_leader_election(self):
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.leader_lock = RedisLockManager(redis_url=redis_url)
        acquired = await self.leader_lock.acquire_lock()
        self.is_leader = acquired
        self.instance_id = self.leader_lock.instance_id
        if acquired:
            print(f"This instance ({self.instance_id}) is the leader.")
        else:
            print(f"This instance ({self.instance_id}) is NOT the leader.")

    async def stop_leader_election(self):
        if self.leader_lock:
            await self.leader_lock.release_lock()
            self.is_leader = False
            self.leader_lock = None

    async def load_jobs_from_db(self):
        await self.crons.load_jobs_from_db()

    async def start(self):
        await self.start_leader_election()
        await self.crons.start()

    async def stop(self):
        await self.crons.stop()
        await self.stop_leader_election() 