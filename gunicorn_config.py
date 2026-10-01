"""Gunicorn configuration for production (Oracle Cloud ARM).

Cargado por la unidad systemd de producción:
``deploy/systemd/orderfox.service`` ejecuta
``gunicorn -c gunicorn_config.py "app:create_app()"`` — este archivo ES la
configuración real de prod (bind 127.0.0.1:8000 tras nginx).

Los entrypoints de Docker (``Dockerfile`` CMD, ``start.sh``,
``docker-compose.yml``) pasan los parámetros por línea de comandos a propósito:
ahí el contenedor necesita ``0.0.0.0:5000`` y logs a stdout/stderr, no archivos
en ``/var/log/orderfox`` ni un bind de loopback.

OJO con ``preload_app = True``: carga la app en el master antes de forkear.
Está acoplado a la decisión pendiente sobre el APScheduler (VLZ-7) — decidir
los dos juntos.
"""
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
