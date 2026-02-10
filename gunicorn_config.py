import multiprocessing
import os

# Puerto del servidor
bind = "0.0.0.0:8000"

# Trabajadores (Workers)
# Fórmula recomendada: (2 x num_cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Hilos (Threads)
threads = 2

# Tiempo de espera (Timeout)
# Aumentar si las cargas de archivos o procesos largos son comunes
timeout = 120

# Archivos de registro (Logs)
accesslog = "-"  # Salida estándar
errorlog = "-"   # Salida estándar de error
loglevel = "info"

# Nombre del proceso
proc_name = "velzia_sass"

# Configuracion SSL (Solo activar en producción real con certificados)
# keyfile = "privkey.pem"
# certfile = "fullchain.pem"
