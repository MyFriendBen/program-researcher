"""
RQ worker settings for Heroku Redis (self-signed SSL certs).
"""

import os

from redis import Redis

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

if redis_url.startswith("rediss://"):
    CONN = Redis.from_url(redis_url, ssl_cert_reqs="none")
else:
    CONN = Redis.from_url(redis_url)

QUEUES = ["research"]
