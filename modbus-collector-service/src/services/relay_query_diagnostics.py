import threading
from collections import deque
from copy import deepcopy


class RelayQueryDiagnostics:
    """Resume las consultas fisicas del lector para la vista de reles."""

    def __init__(self, reader):
        self.reader = reader
        self._state_lock = threading.RLock()
        self._recent_queries = {}
        self._pending_disturbance_page_queries = {}

    def record(self, event: dict) -> None:
        relay_id = int(event["relay_id"])
        address = int(str(event["address"]), 16)
        page = address >> 8
        page_offset = address & 0xFF
        is_disturbance_page = (
            self.reader.DISTURBANCE_PAGE_FIRST <= page <= 0x21
            and int(event["count"]) == self.reader.MODBUS_MAX_READ_WORDS
            and page_offset in {0, self.reader.MODBUS_MAX_READ_WORDS}
        )
        with self._state_lock:
            history = self._recent_queries.setdefault(relay_id, deque(maxlen=4))
            if not is_disturbance_page:
                history.appendleft(deepcopy(event))
                return

            query_key = (relay_id, page)
            if page_offset == 0:
                logical_query = deepcopy(event)
                logical_query["address"] = f"0x{page << 8:04X}"
                logical_query["count"] = self.reader.DISTURBANCE_SAMPLES_PER_PAGE
                logical_query["received_count"] = int(
                    event.get("received_count") or 0
                )
                logical_query["physical_requests"] = 1
                if event["status"] == "ok":
                    self._pending_disturbance_page_queries[query_key] = logical_query
                else:
                    history.appendleft(logical_query)
                return

            first_part = self._pending_disturbance_page_queries.pop(
                query_key,
                None,
            )
            if first_part is None:
                logical_query = deepcopy(event)
                logical_query["address"] = f"0x{page << 8:04X}"
                logical_query["count"] = self.reader.DISTURBANCE_SAMPLES_PER_PAGE
                logical_query["received_count"] = int(
                    event.get("received_count") or 0
                )
                logical_query["physical_requests"] = 1
                history.appendleft(logical_query)
                return

            received_count = int(first_part["received_count"]) + int(
                event.get("received_count") or 0
            )
            first_part["received_count"] = received_count
            first_part["physical_requests"] = 2
            first_part["duration_ms"] = round(
                float(first_part["duration_ms"]) + float(event["duration_ms"]),
                1,
            )
            first_part["timestamp"] = event["timestamp"]
            if event["status"] != "ok":
                first_part["status"] = event["status"]
            history.appendleft(first_part)


    def get_query_snapshot(self, relay_id: int) -> list[dict]:
        with self._state_lock:
            return deepcopy(list(self._recent_queries.get(relay_id, ())))


    def reset(self):
        with self._state_lock:
            self._recent_queries.clear()
            self._pending_disturbance_page_queries.clear()
