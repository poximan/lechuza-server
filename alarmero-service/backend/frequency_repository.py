from .db import _LOCK, _connect


def load_frequency_history():
    with _LOCK, _connect() as connection:
        catalog = connection.execute(
            """
            SELECT c.source_id, c.alarm_key, c.title, c.category,
                   c.catalog_active, MIN(e.occurred_at) AS first_observed_at
            FROM alarm_catalog c
            LEFT JOIN lifecycle_events e
              ON e.source_id = c.source_id AND e.alarm_key = c.alarm_key
            GROUP BY c.source_id, c.alarm_key, c.title, c.category, c.catalog_active;
            """
        ).fetchall()
        incidents = connection.execute(
            """
            SELECT incident_id, source_id, alarm_key, first_seen_at
            FROM incidents
            WHERE qualified_at IS NOT NULL;
            """
        ).fetchall()
    return catalog, incidents
