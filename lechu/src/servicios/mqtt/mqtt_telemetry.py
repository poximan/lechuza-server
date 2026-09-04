from __future__ import annotations

from collections import deque
from copy import deepcopy
from threading import Lock
from typing import Any

from src.utils import timebox


class MqttTrafficTelemetry:
    def __init__(self, max_recent: int = 80):
        self._lock = Lock()
        self._started_at = timebox.utc_iso()
        self._max_recent = int(max_recent)
        self._recent = deque(maxlen=self._max_recent)
        self._topics: dict[str, dict[str, Any]] = {}
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._listeners: dict[str, dict[str, Any]] = {}
        self._sources: dict[str, dict[str, Any]] = {}
        self._totals = {
            "published_count": 0,
            "published_bytes": 0,
            "received_count": 0,
            "received_bytes": 0,
            "subscribe_count": 0,
            "listener_count": 0,
        }

    def record_publish(self, topic: str, payload: Any, qos: int, retain: bool, source: str) -> None:
        topic_key = str(topic)
        source_key = str(source or "lechu")
        payload_bytes = self._payload_size(payload)
        ts = timebox.utc_iso()
        with self._lock:
            stats = self._topic(topic_key)
            stats["published_count"] += 1
            stats["published_bytes"] += payload_bytes
            stats["published_max_bytes"] = max(stats["published_max_bytes"], payload_bytes)
            stats["last_publish_ts"] = ts
            stats["last_qos"] = int(qos)
            stats["last_retain"] = bool(retain)

            source_stats = self._source(source_key)
            source_stats["published_count"] += 1
            source_stats["published_bytes"] += payload_bytes
            source_stats["last_publish_ts"] = ts

            self._totals["published_count"] += 1
            self._totals["published_bytes"] += payload_bytes
            self._recent.appendleft(
                {
                    "ts": ts,
                    "direction": "salida",
                    "topic": topic_key,
                    "source": source_key,
                    "bytes": payload_bytes,
                    "qos": int(qos),
                    "retain": bool(retain),
                }
            )

    def record_receive(self, topic: str, payload: Any) -> None:
        topic_key = str(topic)
        payload_bytes = self._payload_size(payload)
        ts = timebox.utc_iso()
        with self._lock:
            stats = self._topic(topic_key)
            stats["received_count"] += 1
            stats["received_bytes"] += payload_bytes
            stats["received_max_bytes"] = max(stats["received_max_bytes"], payload_bytes)
            stats["last_receive_ts"] = ts

            self._totals["received_count"] += 1
            self._totals["received_bytes"] += payload_bytes
            self._recent.appendleft(
                {
                    "ts": ts,
                    "direction": "entrada",
                    "topic": topic_key,
                    "source": "broker",
                    "bytes": payload_bytes,
                    "qos": None,
                    "retain": None,
                }
            )

    def record_subscription(self, topic: str, qos: int, source: str) -> None:
        topic_key = str(topic)
        source_key = str(source or "lechu")
        ts = timebox.utc_iso()
        with self._lock:
            self._subscriptions[topic_key] = {
                "topic": topic_key,
                "qos": int(qos),
                "source": source_key,
                "ts": ts,
            }
            self._totals["subscribe_count"] += 1
            self._recent.appendleft(
                {
                    "ts": ts,
                    "direction": "suscripcion",
                    "topic": topic_key,
                    "source": source_key,
                    "bytes": 0,
                    "qos": int(qos),
                    "retain": None,
                }
            )

    def record_listener(self, prefix: str, source: str) -> None:
        prefix_key = str(prefix)
        source_key = str(source or "lechu")
        ts = timebox.utc_iso()
        with self._lock:
            self._listeners[prefix_key] = {
                "prefix": prefix_key,
                "source": source_key,
                "ts": ts,
            }
            self._totals["listener_count"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            topics = [deepcopy(item) for item in self._topics.values()]
            subscriptions = [deepcopy(item) for item in self._subscriptions.values()]
            listeners = [deepcopy(item) for item in self._listeners.values()]
            sources = [deepcopy(item) for item in self._sources.values()]
            totals = dict(self._totals)
            recent = list(deepcopy(tuple(self._recent)))

        active_topics = sorted(
            {
                *[item["topic"] for item in topics],
                *[item["topic"] for item in subscriptions],
                *[item["prefix"] for item in listeners],
            }
        )

        return {
            "started_at": self._started_at,
            "totals": totals,
            "active_topics": active_topics,
            "subscriptions": sorted(subscriptions, key=lambda item: item["topic"]),
            "listeners": sorted(listeners, key=lambda item: item["prefix"]),
            "publishers": sorted(
                sources,
                key=lambda item: (item["published_count"], item["published_bytes"]),
                reverse=True,
            ),
            "rank_publicaciones": sorted(
                [item for item in topics if item["published_count"] > 0],
                key=lambda item: item["published_count"],
                reverse=True,
            ),
            "rank_payload_acumulado": sorted(
                [item for item in topics if item["published_bytes"] > 0],
                key=lambda item: item["published_bytes"],
                reverse=True,
            ),
            "rank_payload_maximo": sorted(
                [item for item in topics if item["published_max_bytes"] > 0],
                key=lambda item: item["published_max_bytes"],
                reverse=True,
            ),
            "rank_recepciones": sorted(
                [item for item in topics if item["received_count"] > 0],
                key=lambda item: item["received_count"],
                reverse=True,
            ),
            "recent": recent,
        }

    def _topic(self, topic: str) -> dict[str, Any]:
        if topic not in self._topics:
            self._topics[topic] = {
                "topic": topic,
                "published_count": 0,
                "published_bytes": 0,
                "published_max_bytes": 0,
                "received_count": 0,
                "received_bytes": 0,
                "received_max_bytes": 0,
                "last_publish_ts": None,
                "last_receive_ts": None,
                "last_qos": None,
                "last_retain": None,
            }
        return self._topics[topic]

    def _source(self, source: str) -> dict[str, Any]:
        if source not in self._sources:
            self._sources[source] = {
                "source": source,
                "published_count": 0,
                "published_bytes": 0,
                "last_publish_ts": None,
            }
        return self._sources[source]

    @staticmethod
    def _payload_size(payload: Any) -> int:
        if isinstance(payload, bytes):
            return len(payload)
        if isinstance(payload, str):
            return len(payload.encode("utf-8"))
        return len(str(payload).encode("utf-8"))
