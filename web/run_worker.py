"""
Start the RQ worker with proper Heroku Redis SSL handling.
"""

import os

from redis import Redis
from rq import Queue, Worker

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

if redis_url.startswith("rediss://"):
    conn = Redis.from_url(redis_url, ssl_cert_reqs="none")
else:
    conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    queues = [Queue("research", connection=conn)]
    worker = Worker(queues, connection=conn)
    worker.work()
