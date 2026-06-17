import sqlite3
from .dao_base import get_db_connection, db_lock
from logosaurio import logger

class GrdDAO:
    def insert_grd_description(self, grd_id: int, description: str):
        """
        Inserta una descripcion para un GRD_ID en la tabla 'grd'.
        Usa INSERT OR IGNORE para no insertar si el ID ya existe.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO grd (id, descripcion)
                    VALUES (?, ?)
                ''', (grd_id, description))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info("Descripcion insertada para GRD ID %s: '%s'", grd_id, description, origin="MODBUS/DAO")
            except sqlite3.Error as e:
                logger.error("Error al insertar descripcion GRD: %s", e, origin="MODBUS/DAO")
            finally:
                if conn:
                    conn.close()

    def get_grd_description(self, grd_id: int):
        """
        Obtiene la descripcion de un GRD_ID.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT descripcion FROM grd WHERE id = ?", (grd_id,))
                result = cursor.fetchone()
                return result['descripcion'] if result else None
            except sqlite3.Error as e:
                logger.error("Error al obtener descripcion de GRD %s: %s", grd_id, e, origin="MODBUS/DAO")
                return None
            finally:
                if conn:
                    conn.close()

    def grd_exists(self, grd_id: int) -> bool:
        """
        Verifica si un GRD_ID existe en la tabla 'grd'.
        Retorna True si existe, False en caso contrario.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()        
                cursor.execute("SELECT 1 FROM grd WHERE id = ?", (grd_id,))
                return cursor.fetchone() is not None
            except sqlite3.Error as e:
                logger.error("Error al verificar la existencia de GRD ID %s: %s", grd_id, e, origin="MODBUS/DAO")
                return False
            finally:
                if conn:
                    conn.close()

    def get_all_grds_with_descriptions(self, only_active: bool = False) -> dict:
        """
        Recupera todos los GRD IDs y sus descripciones de la tabla 'grd',
        excluyendo aquellos cuya descripcion sea 'reserva'.
        Si only_active es True, solo retorna los que tienen flag activo=1.
        Retorna un diccionario en formato {grd_id: descripcion}.
        """
        conn = None
        grds_data = {}
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                query = "SELECT id, descripcion FROM grd WHERE descripcion <> 'reserva'"
                params = []
                if only_active:
                    query += " AND activo = 1"
                query += " ORDER BY id ASC;"
                cursor.execute(query, params)
                rows = cursor.fetchall()
                for row in rows:
                    grds_data[row['id']] = row['descripcion']
            except sqlite3.Error as e:
                logger.error("Error al obtener todos los GRD con descripciones: %s", e, origin="MODBUS/DAO")
            finally:
                if conn:
                    conn.close()
        return grds_data

# Instancia de la clase para usar sus metodos
grd_dao = GrdDAO()
