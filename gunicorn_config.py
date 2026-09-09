"""Gunicorn configuration for production (Oracle Cloud ARM)."""
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "/var/log/orderfox/access.log"
errorlog = "/var/log/orderfox/error.log"
loglevel = "info"

# Process naming
proc_name = "orderfox"

# Server mechanics
preload_app = True
daemon = False
