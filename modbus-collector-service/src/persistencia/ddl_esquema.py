import os
import sqlite3
from .dao.dao_base import db_lock, get_db_connection, DATABASE_DIR, DATABASE_FILE
from logosaurio import logger

def create_database_schema():
    """
    Asegura directorio y tablas SQLite:
    - grd
    - historicos
    - mensajes_enviados
    - reles
    - fallas_reles
    Usa el mismo RLock (db_lock) y get_db_connection() de dao_base.
    """
    if not os.path.exists(DATABASE_DIR):
        os.makedirs(DATABASE_DIR, exist_ok=True)
        logger.info("Directorio '%s' creado.", DATABASE_DIR, origin="MODBUS/DB")

    with db_lock:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1) Tabla 'grd'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grd (
                    id INTEGER PRIMARY KEY,
                    descripcion TEXT,
                    activo INTEGER NOT NULL DEFAULT 1
                )
            """)
            logger.info("Tabla 'grd' asegurada.", origin="MODBUS/DB")

            # 2) Tabla 'historicos'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historicos (
                    timestamp TEXT NOT NULL,
                    id_grd INTEGER NOT NULL,
                    conectado INTEGER,
                    PRIMARY KEY (timestamp, id_grd),
                    FOREIGN KEY (id_grd) REFERENCES grd(id)
                )
            """)
            logger.info("Tabla 'historicos' asegurada.", origin="MODBUS/DB")

            # 3) Tabla 'mensajes_enviados'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mensajes_enviados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    message_type TEXT,
                    recipient TEXT,
                    success INTEGER NOT NULL
                )
            """)
            logger.info("Tabla 'mensajes_enviados' asegurada.", origin="MODBUS/DB")

            # 4) Tabla 'reles'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_modbus INTEGER UNIQUE,
                    descripcion TEXT
                )
            """)
            logger.info("Tabla 'reles' asegurada.", origin="MODBUS/DB")

            # 5) Tabla 'fallas_reles'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fallas_reles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_rele INTEGER NOT NULL,
                    numero_falla INTEGER NOT NULL,
                    timestamp DATETIME NOT NULL,
                    fasea_corr INTEGER,
                    faseb_corr INTEGER,
                    fasec_corr INTEGER,
                    tierra_corr INTEGER,
                    FOREIGN KEY (id_rele) REFERENCES reles(id)
                )
            """)
            logger.info("Tabla 'fallas_reles' asegurada.", origin="MODBUS/DB")

            conn.commit()
            logger.info("Esquema de base de datos en %s creado/asegurado.", DATABASE_FILE, origin="MODBUS/DB")
        except sqlite3.Error as e:
            logger.error("Error al configurar el esquema de la base de datos: %s", e, origin="MODBUS/DB")
        finally:
            if conn:
                conn.close()
