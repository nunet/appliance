import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WORKERS", "1"))
preload_app = True

timeout = 60
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOGLEVEL", "info")
forwarded_allow_ips = "*"
