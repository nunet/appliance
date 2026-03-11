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

# Optional TLS configuration (used when running HTTPS via systemd env)
ssl_certfile = os.getenv("SSL_CERTFILE")
ssl_keyfile = os.getenv("SSL_KEYFILE")
if ssl_certfile and ssl_keyfile and os.path.isfile(ssl_certfile) and os.path.isfile(ssl_keyfile):
    certfile = ssl_certfile
    keyfile = ssl_keyfile
