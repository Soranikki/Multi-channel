import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DurableEventStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._init_db()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_events (
                    event_id TEXT PRIMARY KEY,
                    source_event_id TEXT,
                    platform TEXT NOT NULL,
                    shop_id TEXT,
                    external_order_id TEXT,
                    event_type TEXT NOT NULL,
                    raw_payload JSONB NOT NULL,
                    normalized_event JSONB NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    received_at TIMESTAMPTZ NOT NULL,
                    normalized_at TIMESTAMPTZ NOT NULL,
                    delivered_at TIMESTAMPTZ,
                    processed_at TIMESTAMPTZ,
                    next_retry_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT chk_integration_events_status CHECK (
                        status IN ('queued', 'delivering', 'delivered', 'processed', 'failed', 'dead_letter')
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_integration_events_status_retry
                ON integration_events (status, next_retry_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_integration_events_platform_external
                ON integration_events (platform, external_order_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_integration_events_received_at
                ON integration_events (received_at)
                """
            )

    def queue_event(self, raw_event: dict[str, Any], normalized_event: dict[str, Any]) -> None:
        now = utc_now()
        payload = normalized_event.get("payload") or {}
        external_order_id = payload.get("external_order_id")
        shop_id = payload.get("shop_id") or raw_event.get("shop_id")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO integration_events (
                    event_id, source_event_id, platform, shop_id, external_order_id, event_type,
                    raw_payload, normalized_event, status, received_at, normalized_at, next_retry_at
                ) VALUES (
                    %(event_id)s, %(source_event_id)s, %(platform)s, %(shop_id)s, %(external_order_id)s,
                    %(event_type)s, %(raw_payload)s, %(normalized_event)s, 'queued',
                    %(received_at)s, %(normalized_at)s, %(next_retry_at)s
                )
                ON CONFLICT(event_id) DO UPDATE SET
                    source_event_id = EXCLUDED.source_event_id,
                    platform = EXCLUDED.platform,
                    shop_id = EXCLUDED.shop_id,
                    external_order_id = EXCLUDED.external_order_id,
                    event_type = EXCLUDED.event_type,
                    raw_payload = EXCLUDED.raw_payload,
                    normalized_event = EXCLUDED.normalized_event,
                    status = CASE
                        WHEN integration_events.status IN ('delivered', 'processed') THEN integration_events.status
                        ELSE 'queued'
                    END,
                    last_error = NULL,
                    normalized_at = EXCLUDED.normalized_at,
                    next_retry_at = EXCLUDED.next_retry_at,
                    updated_at = NOW()
                """,
                {
                    "event_id": normalized_event["event_id"],
                    "source_event_id": normalized_event.get("source_event_id"),
                    "platform": normalized_event.get("platform"),
                    "shop_id": shop_id,
                    "external_order_id": external_order_id,
                    "event_type": normalized_event.get("event_type"),
                    "raw_payload": Jsonb(raw_event),
                    "normalized_event": Jsonb(normalized_event),
                    "received_at": raw_event.get("received_at") or now,
                    "normalized_at": normalized_event.get("normalized_at") or now,
                    "next_retry_at": now,
                },
            )

    def pending_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT normalized_event
                FROM integration_events
                WHERE status IN ('queued', 'failed')
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY received_at ASC
                LIMIT %(limit)s
                """,
                {"limit": limit},
            ).fetchall()
        return [row["normalized_event"] for row in rows]

    def mark_delivered(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE integration_events
                SET status = 'delivered', delivered_at = NOW(), processed_at = NOW(),
                    last_error = NULL, updated_at = NOW()
                WHERE event_id = %(event_id)s
                """,
                {"event_id": event_id},
            )

    def mark_failed(self, event_id: str, error: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempt_count FROM integration_events WHERE event_id = %(event_id)s",
                {"event_id": event_id},
            ).fetchone()
            attempt_count = (row["attempt_count"] if row else 0) + 1
            delay_minutes = min(60, 2 ** min(attempt_count - 1, 5))
            max_attempts = int(os.getenv("EVENT_MAX_ATTEMPTS", "6"))
            status = "dead_letter" if attempt_count >= max_attempts else "failed"
            conn.execute(
                """
                UPDATE integration_events
                SET status = %(status)s,
                    attempt_count = %(attempt_count)s,
                    last_error = %(last_error)s,
                    next_retry_at = %(next_retry_at)s,
                    updated_at = NOW()
                WHERE event_id = %(event_id)s
                """,
                {
                    "status": status,
                    "attempt_count": attempt_count,
                    "last_error": error,
                    "next_retry_at": utc_now() + timedelta(minutes=delay_minutes),
                    "event_id": event_id,
                },
            )

    def list_events(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT event_id, source_event_id, platform, shop_id, external_order_id, event_type,
                           status, attempt_count, last_error, received_at, normalized_at,
                           delivered_at, next_retry_at, created_at, updated_at
                    FROM integration_events
                    WHERE status = %(status)s
                    ORDER BY received_at DESC
                    LIMIT %(limit)s
                    """,
                    {"status": status, "limit": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_id, source_event_id, platform, shop_id, external_order_id, event_type,
                           status, attempt_count, last_error, received_at, normalized_at,
                           delivered_at, next_retry_at, created_at, updated_at
                    FROM integration_events
                    ORDER BY received_at DESC
                    LIMIT %(limit)s
                    """,
                    {"limit": limit},
                ).fetchall()
        return [dict(row) for row in rows]

    def healthcheck(self) -> bool:
        with self._connect() as conn:
            conn.execute("SELECT 1")
        return True


def build_event_store() -> DurableEventStore:
    database_url = os.getenv(
        "EVENT_DATABASE_URL",
        "postgresql://khanh:nhachung@host.docker.internal:5432/mc_integration",
    )
    return DurableEventStore(database_url)
