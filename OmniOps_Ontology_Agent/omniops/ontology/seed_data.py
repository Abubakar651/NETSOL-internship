"""Deterministic SQLite raw enterprise telemetry and Golden Incident seed database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE raw_teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slack_channel TEXT NOT NULL,
    oncall_engineer TEXT NOT NULL,
    escalation_policy TEXT NOT NULL
);

CREATE TABLE raw_services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version TEXT NOT NULL,
    last_stable_version TEXT NOT NULL,
    error_rate_pct REAL NOT NULL,
    p99_latency_ms INTEGER NOT NULL,
    owner_team_id TEXT NOT NULL,
    FOREIGN KEY (owner_team_id) REFERENCES raw_teams(id)
);

CREATE TABLE raw_endpoints (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    p99_latency_ms INTEGER NOT NULL,
    error_rate_pct REAL NOT NULL,
    sla_latency_ms INTEGER NOT NULL,
    FOREIGN KEY (service_id) REFERENCES raw_services(id)
);

CREATE TABLE raw_databases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,
    active_connections INTEGER NOT NULL,
    max_connections INTEGER NOT NULL,
    cpu_utilization_pct REAL NOT NULL,
    schema_version TEXT NOT NULL
);

CREATE TABLE raw_service_calls (
    caller_service_id TEXT NOT NULL,
    target_service_id TEXT NOT NULL,
    call_type TEXT NOT NULL,
    rpm INTEGER NOT NULL,
    hard_dependency INTEGER NOT NULL,
    PRIMARY KEY (caller_service_id, target_service_id),
    FOREIGN KEY (caller_service_id) REFERENCES raw_services(id),
    FOREIGN KEY (target_service_id) REFERENCES raw_services(id)
);

CREATE TABLE raw_service_databases (
    service_id TEXT NOT NULL,
    database_id TEXT NOT NULL,
    access_mode TEXT NOT NULL,
    pool_size INTEGER NOT NULL,
    PRIMARY KEY (service_id, database_id),
    FOREIGN KEY (service_id) REFERENCES raw_services(id),
    FOREIGN KEY (database_id) REFERENCES raw_databases(id)
);

CREATE TABLE raw_pull_requests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    target_service_id TEXT NOT NULL,
    deployed_version TEXT NOT NULL,
    merged_at TEXT NOT NULL,
    changed_files TEXT NOT NULL,
    touches_db_config INTEGER NOT NULL,
    touches_schema INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    migrates_database_id TEXT,
    FOREIGN KEY (target_service_id) REFERENCES raw_services(id),
    FOREIGN KEY (migrates_database_id) REFERENCES raw_databases(id)
);

CREATE TABLE raw_incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    affected_service_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    symptom_summary TEXT NOT NULL,
    root_cause_pr_id TEXT,
    FOREIGN KEY (affected_service_id) REFERENCES raw_services(id),
    FOREIGN KEY (root_cause_pr_id) REFERENCES raw_pull_requests(id)
);

CREATE TABLE raw_wifi_telemetry (
    sensor_id TEXT PRIMARY KEY,
    floor TEXT NOT NULL,
    packet_loss_pct REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
"""


def create_seeded_database(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Create and seed an isolated SQLite database containing raw enterprise tables."""
    target = str(db_path)
    if target != ":memory:":
        path_obj = Path(target)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        if path_obj.exists():
            path_obj.unlink()

    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)

    teams = [
        ("TEAM-PAYMENTS", "Core Payments & Ledger Engineering", "#alerts-payments", "sre-payments@netsol.example", "PagerDuty-Tier1-5m"),
        ("TEAM-PLATFORM", "Edge Gateway & Platform Core", "#alerts-platform", "sre-platform@netsol.example", "PagerDuty-Tier1-5m"),
        ("TEAM-RISK", "Fraud Scoring & Risk Intelligence", "#alerts-risk", "sre-risk@netsol.example", "PagerDuty-Tier2-15m"),
    ]
    conn.executemany("INSERT INTO raw_teams VALUES (?, ?, ?, ?, ?)", teams)

    services = [
        ("SVC-MOBILE-GW", "MobileAppGateway", "P0", "DEGRADED", "v3.1.2", "v3.1.1", 9.5, 920, "TEAM-PLATFORM"),
        ("SVC-WEB-STORE", "WebStorefront", "P0", "DEGRADED", "v4.0.1", "v4.0.0", 7.2, 840, "TEAM-PLATFORM"),
        ("SVC-CHECKOUT", "CheckoutService", "P0", "DEGRADED", "v2.1.0", "v2.0.9", 14.1, 1850, "TEAM-PAYMENTS"),
        ("SVC-PAYMENT-GW", "PaymentGatewayService", "P0", "CRITICAL", "v2.5.0", "v2.4.1", 18.4, 2450, "TEAM-PAYMENTS"),
        ("SVC-FRAUD-ENGINE", "FraudDetectionService", "P1", "DEGRADED", "v1.9.0", "v1.8.4", 4.8, 3100, "TEAM-RISK"),
        ("SVC-NOTIFICATION", "NotificationWorker", "P2", "HEALTHY", "v1.3.0", "v1.2.9", 0.1, 120, "TEAM-PLATFORM"),
    ]
    conn.executemany("INSERT INTO raw_services VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", services)

    endpoints = [
        ("EP-MOBILE-PAY", "SVC-MOBILE-GW", "POST", "/mobile/v2/checkout/pay", 940, 9.8, 350),
        ("EP-WEB-CHECKOUT", "SVC-WEB-STORE", "POST", "/web/checkout/submit", 860, 7.4, 400),
        ("EP-CHECKOUT-ORDER", "SVC-CHECKOUT", "POST", "/api/v1/orders/finalize", 1890, 14.3, 450),
        ("EP-PAY-CHARGE", "SVC-PAYMENT-GW", "POST", "/api/v1/payments/charge", 2600, 22.1, 300),
        ("EP-FRAUD-SCORE", "SVC-FRAUD-ENGINE", "POST", "/rpc/fraud/score", 3150, 5.1, 250),
        ("EP-NOTIFY-SEND", "SVC-NOTIFICATION", "POST", "/internal/notify/dispatch", 125, 0.1, 500),
    ]
    conn.executemany("INSERT INTO raw_endpoints VALUES (?, ?, ?, ?, ?, ?, ?)", endpoints)

    databases = [
        ("DB-ACCOUNT-LEDGER", "AccountLedgerDB", "PostgreSQL", "HIGH_LOAD", 498, 500, 94.2, "v14"),
        ("DB-ORDER-STORE", "OrderStoreDB", "PostgreSQL", "HIGH_LOAD", 240, 400, 88.5, "v22"),
        ("DB-SESSION-REDIS", "SessionCacheRedis", "Redis", "HIGH_LOAD", 480, 500, 82.0, "v7"),
    ]
    conn.executemany("INSERT INTO raw_databases VALUES (?, ?, ?, ?, ?, ?, ?, ?)", databases)

    service_calls = [
        ("SVC-MOBILE-GW", "SVC-CHECKOUT", "SYNC_HTTP", 1450, 1),
        ("SVC-WEB-STORE", "SVC-CHECKOUT", "SYNC_HTTP", 1120, 1),
        ("SVC-CHECKOUT", "SVC-PAYMENT-GW", "GRPC", 2300, 1),
        ("SVC-PAYMENT-GW", "SVC-FRAUD-ENGINE", "GRPC", 2280, 1),
        ("SVC-PAYMENT-GW", "SVC-NOTIFICATION", "ASYNC_EVENT", 1900, 0),
    ]
    conn.executemany("INSERT INTO raw_service_calls VALUES (?, ?, ?, ?, ?)", service_calls)

    service_databases = [
        ("SVC-PAYMENT-GW", "DB-ACCOUNT-LEDGER", "READ_WRITE", 200),
        ("SVC-CHECKOUT", "DB-ORDER-STORE", "READ_WRITE", 80),
        ("SVC-FRAUD-ENGINE", "DB-ORDER-STORE", "READ_ONLY", 60),
        ("SVC-MOBILE-GW", "DB-SESSION-REDIS", "READ_WRITE", 150),
        ("SVC-WEB-STORE", "DB-SESSION-REDIS", "READ_WRITE", 120),
    ]
    conn.executemany("INSERT INTO raw_service_databases VALUES (?, ?, ?, ?)", service_databases)

    pull_requests = [
        (
            "PR-882",
            "Refactor ledger DB connection pool & disable idle reaper",
            "dev.alex",
            "SVC-PAYMENT-GW",
            "v2.5.0",
            "2026-11-24T17:38:00+00:00",
            json.dumps(["payment_gw/db/connection_pool.py", "config/pool.yaml"]),
            1,
            0,
            "HIGH",
            None,
        ),
        (
            "PR-879",
            "Add fraud_risk_audit JSONB column migration without index",
            "dev.sara",
            "SVC-FRAUD-ENGINE",
            "v1.9.0",
            "2026-11-24T17:13:00+00:00",
            json.dumps(["migrations/20261124_fraud_audit.sql", "fraud/scoring.py"]),
            0,
            1,
            "HIGH",
            "DB-ORDER-STORE",
        ),
        (
            "PR-885",
            "Increase mobile session prefetch fanout",
            "dev.omar",
            "SVC-MOBILE-GW",
            "v3.1.2",
            "2026-11-24T17:25:00+00:00",
            json.dumps(["mobile_gw/session_cache.py", "config/redis.yaml"]),
            1,
            0,
            "MEDIUM",
            None,
        ),
        (
            "PR-875",
            "Add promo banner telemetry tag",
            "dev.alina",
            "SVC-CHECKOUT",
            "v2.1.0",
            "2026-11-24T14:00:00+00:00",
            json.dumps(["checkout/ui/promo_banner.py"]),
            0,
            0,
            "LOW",
            None,
        ),
        (
            "PR-871",
            "Update footer copyright label",
            "dev.zain",
            "SVC-WEB-STORE",
            "v4.0.1",
            "2026-11-24T13:00:00+00:00",
            json.dumps(["web/templates/footer.html"]),
            0,
            0,
            "LOW",
            None,
        ),
        (
            "PR-870",
            "Add retry jitter on webhook delivery",
            "dev.hassan",
            "SVC-NOTIFICATION",
            "v1.3.0",
            "2026-11-24T12:00:00+00:00",
            json.dumps(["notifications/webhook_worker.py"]),
            0,
            0,
            "LOW",
            None,
        ),
    ]
    conn.executemany(
        "INSERT INTO raw_pull_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        pull_requests,
    )

    incidents = [
        (
            "INC-409",
            "PaymentGateway 500 errors & pool exhaustion",
            "SEV1",
            "OPEN",
            "SVC-PAYMENT-GW",
            "2026-11-24T18:00:00+00:00",
            "HTTP 500 spike; FATAL: remaining connection slots reserved on AccountLedgerDB",
            None,
        ),
        (
            "INC-512",
            "FraudEngine latency spike & full table scans on OrderStore",
            "SEV2",
            "OPEN",
            "SVC-FRAUD-ENGINE",
            "2026-11-24T18:00:00+00:00",
            "p99 latency 3100ms; sequential scan on fraud_risk_audit JSONB column",
            None,
        ),
        (
            "INC-601",
            "MobileGateway session timeouts & Redis connection saturation",
            "SEV2",
            "OPEN",
            "SVC-MOBILE-GW",
            "2026-11-24T18:00:00+00:00",
            "Session timeout errors; SessionCacheRedis at 480/500 connections",
            None,
        ),
    ]
    conn.executemany("INSERT INTO raw_incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?)", incidents)

    wifi_rows = [
        ("WIFI-FL3-01", "Floor-3", 12.4, "2026-11-24T17:55:00+00:00"),
        ("WIFI-FL4-02", "Floor-4", 1.8, "2026-11-24T17:56:00+00:00"),
    ]
    conn.executemany("INSERT INTO raw_wifi_telemetry VALUES (?, ?, ?, ?)", wifi_rows)

    conn.commit()
    return conn
