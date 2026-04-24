import sqlite3
from .dao_base import get_db_connection, db_lock # Importa las funciones y variables de dao_base
from logosaurio import logger

class RelesDAO:
    """
    Clase DAO para interactuar con la tabla 'reles' en la base de datos SQLite.
    Se adapta al esquema donde 'id' es la PK AUTOINCREMENT y 'id_modbus' es una columna UNIQUE.
    Utiliza get_db_connection y db_lock de dao_base.
    """
    def __init__(self):
        pass

    def insert_rele_description(self, id_modbus: int, description: str):
        """
        Inserta una descripcion de rele en la tabla 'reles'.
        Utiliza INSERT OR IGNORE para evitar duplicados si el id_modbus ya existe,
        permitiendo que el 'id' auto-incremente.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # PRAGMA foreign_keys = ON; se asume que ya se maneja en get_db_connection o ddl_esquema

                cursor.execute('''
                    INSERT OR IGNORE INTO reles (id_modbus, descripcion)
                    VALUES (?, ?)
                ''', (id_modbus, description))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(
                        "Rele (ID Modbus: %s, Desc: '%s') insertado/asegurado en la tabla 'reles'.",
                        id_modbus,
                        description,
                        origin="MODBUS/DAO",
                    )
            except sqlite3.Error as e:
                logger.error("ERROR al insertar rele en la base de datos: %s", e, origin="MODBUS/DAO")
            finally:
                if conn:
                    conn.close()

    def get_rele_description(self, id_modbus: int) -> str | None:
        """
        Obtiene la descripcion de un rele por su id_modbus.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT descripcion FROM reles WHERE id_modbus = ?", (id_modbus,))
                result = cursor.fetchone()
                return result['descripcion'] if result else None # Acceso por nombre de columna
            except sqlite3.Error as e:
                logger.error("ERROR al obtener descripcion de rele: %s", e, origin="MODBUS/DAO")
                return None
            finally:
                if conn:
                    conn.close()

    def rele_exists(self, id_modbus: int) -> bool:
        """
        Verifica si un rele con el id_modbus dado ya existe en la base de datos.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM reles WHERE id_modbus = ?", (id_modbus,))
                return cursor.fetchone() is not None
            except sqlite3.Error as e:
                logger.error("ERROR al verificar existencia de rele: %s", e, origin="MODBUS/DAO")
                return False
            finally:
                if conn:
                    conn.close()

    def get_internal_id_by_modbus_id(self, id_modbus: int) -> int | None:
        """
        Obtiene el ID interno (clave primaria 'id') de un rele dado su id_modbus.
        Esto es necesario para insertar en tablas que referencian 'reles.id'.
        """
        conn = None
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM reles WHERE id_modbus = ?", (id_modbus,))
                result = cursor.fetchone()
                return result['id'] if result else None # Acceso por nombre de columna
            except sqlite3.Error as e:
                logger.error("ERROR al obtener ID interno del rele por id_modbus: %s", e, origin="MODBUS/DAO")
                return None
            finally:
                if conn:
                    conn.close()

    def get_all_reles_with_descriptions(self) -> dict:
        """
        Recupera todos los IDs Modbus de reles y sus descripciones de la tabla 'reles',
        excluyendo aquellos cuya descripcion sea 'NO APLICA'.
        Retorna un diccionario en formato {id_modbus: descripcion}.
        """
        conn = None
        reles_data = {}
        with db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id_modbus, descripcion FROM reles WHERE descripcion <> 'NO APLICA' ORDER BY id_modbus ASC;")
                rows = cursor.fetchall()
                for row in rows:
                    reles_data[row['id_modbus']] = row['descripcion']
            except sqlite3.Error as e:
                logger.error("Error al obtener todos los reles con descripciones: %s", e, origin="MODBUS/DAO")
            finally:
                if conn:
                    conn.close()
        return reles_data

# Instancia global del DAO para reles
reles_dao = RelesDAO()
