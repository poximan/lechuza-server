import sqlite3
import os
import threading
from src import config  # Importa la configuracion

# Rutas de la base de datos usando config.py
DATABASE_DIR = config.DATABASE_DIR
DATABASE_FILE = os.path.join(DATABASE_DIR, config.DATABASE_NAME)

# Bloqueo para asegurar la seguridad de los hilos al escribir/leer en la base de datos.
db_lock = threading.RLock()                     # Usar RLock para permitir bloqueos anidados

def get_db_connection():
    """Crea y retorna una conexion a la base de datos."""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row              # Permite acceder a columnas por nombre
    conn.execute("PRAGMA foreign_keys = ON;")   # Asegura que las FK esten habilitadas en cada conexion
    return conn
