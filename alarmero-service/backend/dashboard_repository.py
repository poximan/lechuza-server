from .db import _LOCK, _connect


def load_dashboard(boundaries):
    with _LOCK, _connect() as connection:
        count_rows = connection.execute(
            "SELECT status, COUNT(*) AS total FROM incidents GROUP BY status;"
        ).fetchall()
        condition_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN current_condition = 1 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN current_condition = 0 THEN 1 ELSE 0 END) AS inactive,
                SUM(CASE WHEN current_condition IS NULL THEN 1 ELSE 0 END) AS unknown
            FROM alarm_catalog
            WHERE catalog_active = 1;
            """
        ).fetchone()
        frequency_rows = connection.execute(
            """
            SELECT c.source_id, c.alarm_key, c.title, c.category,
                   COUNT(i.incident_id) AS total,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS daily,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS weekly,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS monthly,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS annual
            FROM alarm_catalog c
            LEFT JOIN incidents i
              ON i.source_id = c.source_id
             AND i.alarm_key = c.alarm_key
             AND i.qualified_at IS NOT NULL
            WHERE c.catalog_active = 1
            GROUP BY c.source_id, c.alarm_key, c.title, c.category
            ORDER BY total DESC, c.source_id, c.alarm_key;
            """,
            boundaries,
        ).fetchall()
        lifetime_rows = connection.execute(
            """
            SELECT c.source_id, c.alarm_key, c.title, c.category,
                   c.expected_clearance_minutes,
                   i.qualified_at, i.resolved_at
            FROM alarm_catalog c
            LEFT JOIN incidents i
              ON i.source_id = c.source_id
             AND i.alarm_key = c.alarm_key
             AND i.qualified_at IS NOT NULL
            WHERE c.catalog_active = 1
            ORDER BY c.source_id, c.alarm_key, i.qualified_at;
            """
        ).fetchall()

    return count_rows, condition_row, frequency_rows, lifetime_rows
