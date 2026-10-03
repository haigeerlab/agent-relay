#!/usr/bin/env python3
"""Private authorization and control state for same-Mac host delegation.

This module deliberately contains no host launcher and no mailbox reader.  A
mailbox delivery is communication evidence, never delegation authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Callable, Iterator
from uuid import UUID, uuid4


DATABASE_FILENAME = "delegation.sqlite"
SCHEMA_VERSION = 2
HORIZONS = frozenset(("task", "strict", "batch", "session"))
HOSTS = frozenset(("claude", "codex"))
PERMISSION_INTENTS = frozenset(("safe-review", "bounded-development", "host-native"))
AUTHORITIES = frozenset(("direct-user", "confirmed-user", "agent-proposed", "mailbox"))
AUTHORIZATION_STATES = frozenset(("authorized", "cancelled", "expired"))
DELEGATION_STATES = frozenset(
    ("creating", "created", "registered", "running", "completed", "cancelled", "unknown")
)
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_EXPECTED_TABLES = frozenset(("authorizations", "delegations"))
_TRANSITIONS = {
    "creating": frozenset(("created", "unknown", "cancelled")),
    "created": frozenset(("registered", "unknown", "cancelled")),
    "registered": frozenset(("running", "unknown", "cancelled")),
    "running": frozenset(("completed", "unknown", "cancelled")),
    "unknown": frozenset(("created", "registered", "running", "completed", "cancelled")),
    "completed": frozenset(("unknown", "cancelled")),
    "cancelled": frozenset(),
}
_STATE_EVIDENCE = {
    "created": "host-created",
    "registered": "host-registered",
    "running": "host-running",
    "completed": "host-completed",
    "cancelled": "host-cancelled",
    "unknown": "host-result-unknown",
}


class DelegationError(ValueError):
    """The request is unauthorized, ambiguous, stale, or stored unsafely."""


@dataclass(frozen=True)
class AuthorizationRequest:
    authority: str
    horizon: str
    origin_host: str
    origin_session: str
    project_root: Path
    repo_identity: str
    baseline: str
    dirty: bool
    target_hosts: tuple[str, ...]
    permission_intent: str
    host_permission: str | None
    max_sessions: int
    expires_at: int
    depth: int
    idempotency_key: str
    summary: str


@dataclass(frozen=True)
class AuthorizationDecision:
    state: str
    missing_decisions: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class AuthorizationEnvelope:
    envelope_id: str
    idempotency_key: str
    horizon: str
    origin_host: str
    origin_session: str
    project_root: Path
    repo_identity: str
    baseline: str
    dirty: bool
    target_hosts: tuple[str, ...]
    permission_intent: str
    host_permission: str | None
    max_sessions: int
    expires_at: int
    depth: int
    summary: str
    state: str


@dataclass(frozen=True)
class DelegationClaim:
    delegation_id: str
    envelope_id: str
    launch_key: str
    target_host: str
    permission_intent: str
    friendly_name: str
    state: str
    host_ref: str | None
    host_session_ref: str | None
    host_version: str | None
    actual_permission: str | None
    last_turn_ref: str | None


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _valid_text(value: object, *, maximum: int) -> bool:
    return (isinstance(value, str) and 0 < len(value.strip()) <= maximum
            and not _has_control_characters(value))


def _canonical_project(path: Path) -> Path:
    try:
        project = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as error:
        raise DelegationError("project-scope: project root is unavailable") from error
    if not project.is_dir():
        raise DelegationError("project-scope: project root must be a directory")
    return project


def evaluate_authorization(request: AuthorizationRequest, *, now: int | None = None
                           ) -> AuthorizationDecision:
    """Evaluate only explicit control-plane facts; never interpret message text."""
    current = int(time.time()) if now is None else int(now)
    if isinstance(request.authority, str) and request.authority == "mailbox":
        return AuthorizationDecision("rejected", reason="mailbox-is-not-authority")
    if not isinstance(request.authority, str) or request.authority not in AUTHORITIES:
        return AuthorizationDecision("rejected", reason="authority-invalid")
    if request.depth != 0:
        return AuthorizationDecision("rejected", reason="descendant-delegation-disabled")
    if not isinstance(request.horizon, str) or request.horizon not in HORIZONS:
        return AuthorizationDecision("rejected", reason="authorization-horizon")
    if not isinstance(request.origin_host, str) or request.origin_host not in HOSTS:
        return AuthorizationDecision("rejected", reason="origin-host")
    if not _valid_text(request.origin_session, maximum=256):
        return AuthorizationDecision("rejected", reason="origin-session")
    try:
        _canonical_project(request.project_root)
    except DelegationError as error:
        return AuthorizationDecision("rejected", reason=str(error).split(":", 1)[0])
    for value, label, maximum in (
        (request.repo_identity, "repo-identity", 512),
        (request.baseline, "baseline", 256),
        (request.summary, "summary", 500),
    ):
        if not _valid_text(value, maximum=maximum):
            return AuthorizationDecision("rejected", reason=label)
    if not isinstance(request.dirty, bool):
        return AuthorizationDecision("rejected", reason="dirty-state")
    if not request.target_hosts:
        return AuthorizationDecision("decision-required", ("target-host",))
    if (not isinstance(request.target_hosts, tuple)
            or any(not isinstance(host, str) for host in request.target_hosts)
            or len(set(request.target_hosts)) != len(request.target_hosts)
            or any(host not in HOSTS for host in request.target_hosts)):
        return AuthorizationDecision("rejected", reason="target-host")
    if (not isinstance(request.permission_intent, str)
            or request.permission_intent not in PERMISSION_INTENTS):
        return AuthorizationDecision("rejected", reason="permission-intent")
    if request.permission_intent == "host-native":
        if not _valid_text(request.host_permission, maximum=128):
            return AuthorizationDecision("rejected", reason="host-permission")
    elif request.host_permission is not None:
        return AuthorizationDecision("rejected", reason="host-permission-unexpected")
    if (not isinstance(request.max_sessions, int) or isinstance(request.max_sessions, bool)
            or request.max_sessions < 1):
        return AuthorizationDecision("rejected", reason="session-limit")
    if request.horizon != "batch" and request.max_sessions != 1:
        return AuthorizationDecision("rejected", reason="session-limit")
    if (not isinstance(request.expires_at, int) or isinstance(request.expires_at, bool)
            or request.expires_at <= current):
        return AuthorizationDecision("rejected", reason="authorization-expired")
    if (not isinstance(request.idempotency_key, str)
            or not _KEY.fullmatch(request.idempotency_key)):
        return AuthorizationDecision("rejected", reason="idempotency-key")
    if request.authority == "agent-proposed":
        return AuthorizationDecision("decision-required", ("user-authorization",))
    return AuthorizationDecision("authorized")


def _request_payload(request: AuthorizationRequest) -> dict[str, object]:
    return {
        "authority": request.authority,
        "horizon": request.horizon,
        "originHost": request.origin_host,
        "originSession": request.origin_session,
        "projectRoot": str(_canonical_project(request.project_root)),
        "repoIdentity": request.repo_identity,
        "baseline": request.baseline,
        "dirty": request.dirty,
        "targetHosts": sorted(request.target_hosts),
        "permissionIntent": request.permission_intent,
        "hostPermission": request.host_permission,
        "maxSessions": request.max_sessions,
        "expiresAt": request.expires_at,
        "depth": request.depth,
        "summary": request.summary,
    }


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _permission_within(granted: str, requested: str) -> bool:
    if granted == "bounded-development":
        return requested in ("safe-review", "bounded-development")
    return requested == granted


def _is_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _authorization_row_is_valid(row: sqlite3.Row) -> bool:
    try:
        targets = json.loads(row["target_hosts"])
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        _is_uuid(row["envelope_id"])
        and isinstance(row["idempotency_key"], str)
        and _KEY.fullmatch(row["idempotency_key"]) is not None
        and isinstance(row["request_digest"], str)
        and re.fullmatch(r"[0-9a-f]{64}", row["request_digest"]) is not None
        and row["horizon"] in HORIZONS
        and row["origin_host"] in HOSTS
        and _valid_text(row["origin_session"], maximum=256)
        and isinstance(row["project_root"], str)
        and Path(row["project_root"]).is_absolute()
        and _valid_text(row["repo_identity"], maximum=512)
        and _valid_text(row["baseline"], maximum=256)
        and row["dirty"] in (0, 1)
        and isinstance(targets, list)
        and bool(targets)
        and all(isinstance(host, str) for host in targets)
        and len(set(targets)) == len(targets)
        and all(host in HOSTS for host in targets)
        and row["permission_intent"] in PERMISSION_INTENTS
        and ((row["permission_intent"] == "host-native"
              and _valid_text(row["host_permission"], maximum=128))
             or (row["permission_intent"] != "host-native"
                 and row["host_permission"] is None))
        and isinstance(row["max_sessions"], int) and row["max_sessions"] >= 1
        and isinstance(row["expires_at"], int)
        and row["depth"] == 0
        and _valid_text(row["summary"], maximum=500)
        and row["state"] in AUTHORIZATION_STATES
        and isinstance(row["created_at"], int)
        and isinstance(row["updated_at"], int)
    )


def _delegation_row_is_valid(row: sqlite3.Row) -> bool:
    binding = (
        row["host_ref"], row["host_session_ref"], row["host_version"],
        row["actual_permission"],
    )
    return (
        _is_uuid(row["delegation_id"])
        and _is_uuid(row["envelope_id"])
        and isinstance(row["launch_key"], str)
        and _KEY.fullmatch(row["launch_key"]) is not None
        and row["target_host"] in HOSTS
        and row["permission_intent"] in PERMISSION_INTENTS
        and _valid_text(row["friendly_name"], maximum=128)
        and row["state"] in DELEGATION_STATES
        and all(value is None or _valid_text(value, maximum=512) for value in binding)
        and (row["last_turn_ref"] is None
             or _valid_text(row["last_turn_ref"], maximum=512))
        and (row["state"] not in ("created", "registered", "running", "completed")
             or all(value is not None for value in binding))
        and isinstance(row["created_at"], int)
        and isinstance(row["updated_at"], int)
    )


class DelegationStore:
    """Owner-only SQLite store with atomic authorization and launch claims."""

    def __init__(self, root: Path, *, now: Callable[[], int] | None = None):
        self.root = Path(root)
        self.database = self.root / DATABASE_FILENAME
        self._now = now or (lambda: int(time.time()))
        self._prepare_root()
        self._prepare_database()

    def _prepare_root(self) -> None:
        if self.root.exists() or self.root.is_symlink():
            try:
                metadata = self.root.lstat()
            except OSError as error:
                raise DelegationError("state directory is unavailable") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise DelegationError("state directory must not be a symbolic link")
            if not stat.S_ISDIR(metadata.st_mode):
                raise DelegationError("state path must be a directory")
            if metadata.st_uid != os.getuid():
                raise DelegationError("state directory must belong to the current user")
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                raise DelegationError("state directory must have mode 0700")
            return
        try:
            self.root.mkdir(parents=True, mode=0o700)
            self.root.chmod(0o700)
        except OSError as error:
            raise DelegationError("state directory could not be created") from error
        metadata = self.root.lstat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise DelegationError("state directory must belong to the current user with mode 0700")

    def _database_metadata(self) -> os.stat_result:
        try:
            metadata = self.database.lstat()
        except OSError as error:
            raise DelegationError("delegation database is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise DelegationError("delegation database must not be a symbolic link")
        if not stat.S_ISREG(metadata.st_mode):
            raise DelegationError("delegation database must be a regular file")
        if metadata.st_uid != os.getuid():
            raise DelegationError("delegation database must belong to the current user")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise DelegationError("delegation database must have mode 0600")
        return metadata

    def _prepare_database(self) -> None:
        created = False
        if self.database.exists() or self.database.is_symlink():
            self._database_metadata()
        else:
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(self.database, flags, 0o600)
                os.close(descriptor)
                self.database.chmod(0o600)
                created = True
            except OSError as error:
                raise DelegationError("delegation database could not be created") from error
        try:
            if created:
                self._initialize_schema()
            self._validate_schema()
        except DelegationError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise DelegationError("delegation database is corrupt") from error

    def _raw_connection(self) -> sqlite3.Connection:
        self._prepare_root()
        self._database_metadata()
        self._check_sidecars()
        try:
            connection = sqlite3.connect(str(self.database), timeout=5, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            return connection
        except sqlite3.Error as error:
            raise DelegationError("delegation database is corrupt") from error

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._raw_connection()
        try:
            yield connection
        finally:
            connection.close()
            self._check_sidecars()

    def _check_sidecars(self) -> None:
        for suffix in ("-journal", "-wal", "-shm"):
            path = Path(str(self.database) + suffix)
            if not path.exists() and not path.is_symlink():
                continue
            metadata = path.lstat()
            if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600):
                raise DelegationError("delegation database sidecar is unsafe")

    def _initialize_schema(self) -> None:
        with self._connection() as connection:
            try:
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE authorizations (
                        envelope_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        request_digest TEXT NOT NULL,
                        horizon TEXT NOT NULL,
                        origin_host TEXT NOT NULL,
                        origin_session TEXT NOT NULL,
                        project_root TEXT NOT NULL,
                        repo_identity TEXT NOT NULL,
                        baseline TEXT NOT NULL,
                        dirty INTEGER NOT NULL,
                        target_hosts TEXT NOT NULL,
                        permission_intent TEXT NOT NULL,
                        host_permission TEXT,
                        max_sessions INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        depth INTEGER NOT NULL,
                        summary TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    );
                    CREATE TABLE delegations (
                        delegation_id TEXT PRIMARY KEY,
                        envelope_id TEXT NOT NULL REFERENCES authorizations(envelope_id),
                        launch_key TEXT NOT NULL UNIQUE,
                        target_host TEXT NOT NULL,
                        permission_intent TEXT NOT NULL,
                        friendly_name TEXT NOT NULL,
                        state TEXT NOT NULL,
                        host_ref TEXT,
                        host_session_ref TEXT,
                        host_version TEXT,
                        actual_permission TEXT,
                        last_turn_ref TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    );
                    PRAGMA user_version = 2;
                    COMMIT;
                    """
                )
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def _validate_schema(self) -> None:
        self._database_metadata()
        try:
            with self._connection() as connection:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise DelegationError("delegation database is corrupt")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if version != SCHEMA_VERSION or not _EXPECTED_TABLES.issubset(tables):
                    raise DelegationError("delegation database schema is incomplete")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise DelegationError("delegation database contents are invalid")
                if (any(not _authorization_row_is_valid(row) for row in
                        connection.execute("SELECT * FROM authorizations"))
                        or any(not _delegation_row_is_valid(row) for row in
                               connection.execute("SELECT * FROM delegations"))):
                    raise DelegationError("delegation database contents are invalid")
        except DelegationError:
            raise
        except sqlite3.Error as error:
            raise DelegationError("delegation database is corrupt") from error

    @staticmethod
    def _envelope(row: sqlite3.Row) -> AuthorizationEnvelope:
        return AuthorizationEnvelope(
            envelope_id=row["envelope_id"],
            idempotency_key=row["idempotency_key"],
            horizon=row["horizon"],
            origin_host=row["origin_host"],
            origin_session=row["origin_session"],
            project_root=Path(row["project_root"]),
            repo_identity=row["repo_identity"],
            baseline=row["baseline"],
            dirty=bool(row["dirty"]),
            target_hosts=tuple(json.loads(row["target_hosts"])),
            permission_intent=row["permission_intent"],
            host_permission=row["host_permission"],
            max_sessions=row["max_sessions"],
            expires_at=row["expires_at"],
            depth=row["depth"],
            summary=row["summary"],
            state=row["state"],
        )

    @staticmethod
    def _claim(row: sqlite3.Row) -> DelegationClaim:
        return DelegationClaim(
            delegation_id=row["delegation_id"],
            envelope_id=row["envelope_id"],
            launch_key=row["launch_key"],
            target_host=row["target_host"],
            permission_intent=row["permission_intent"],
            friendly_name=row["friendly_name"],
            state=row["state"],
            host_ref=row["host_ref"],
            host_session_ref=row["host_session_ref"],
            host_version=row["host_version"],
            actual_permission=row["actual_permission"],
            last_turn_ref=row["last_turn_ref"],
        )

    def authorize(self, request: AuthorizationRequest) -> AuthorizationEnvelope:
        decision = evaluate_authorization(request, now=self._now())
        if decision.state != "authorized":
            reason = decision.reason or ",".join(decision.missing_decisions)
            raise DelegationError(reason)
        payload = _request_payload(request)
        digest = _digest(payload)
        current = int(self._now())
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM authorizations WHERE idempotency_key = ?",
                    (request.idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if existing["request_digest"] != digest:
                        raise DelegationError("idempotency-conflict")
                    connection.execute("COMMIT")
                    return self._envelope(existing)
                envelope_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO authorizations (
                        envelope_id, idempotency_key, request_digest, horizon,
                        origin_host, origin_session, project_root, repo_identity,
                        baseline, dirty, target_hosts, permission_intent,
                        host_permission, max_sessions, expires_at, depth, summary,
                        state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        envelope_id, request.idempotency_key, digest, request.horizon,
                        request.origin_host, request.origin_session,
                        payload["projectRoot"], request.repo_identity, request.baseline,
                        int(request.dirty), json.dumps(payload["targetHosts"]),
                        request.permission_intent, request.host_permission,
                        request.max_sessions, request.expires_at, request.depth,
                        request.summary, "authorized", current, current,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM authorizations WHERE envelope_id = ?", (envelope_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._envelope(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def _load_envelope(self, connection: sqlite3.Connection,
                       envelope_id: str) -> AuthorizationEnvelope:
        row = connection.execute(
            "SELECT * FROM authorizations WHERE envelope_id = ?", (envelope_id,)
        ).fetchone()
        if row is None:
            raise DelegationError("authorization-not-found")
        envelope = self._envelope(row)
        if envelope.state == "authorized" and envelope.expires_at <= int(self._now()):
            connection.execute(
                "UPDATE authorizations SET state = 'expired', updated_at = ? WHERE envelope_id = ?",
                (int(self._now()), envelope_id),
            )
            envelope = AuthorizationEnvelope(**{**envelope.__dict__, "state": "expired"})
        return envelope

    def get_authorization(self, envelope_id: str) -> AuthorizationEnvelope:
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                envelope = self._load_envelope(connection, envelope_id)
                connection.execute("COMMIT")
                return envelope
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def claim_launch(
        self, envelope_id: str, launch_key: str, target_host: str,
        project_root: Path, baseline: str, permission_intent: str, *,
        confirmed: bool = False, friendly_name: str | None = None,
    ) -> DelegationClaim:
        if not isinstance(launch_key, str) or not _KEY.fullmatch(launch_key):
            raise DelegationError("launch-key")
        project = _canonical_project(project_root)
        selected_name = friendly_name or (
            "Claude Code session" if target_host == "claude" else "Codex session")
        if not _valid_text(selected_name, maximum=128):
            raise DelegationError("friendly-name")
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                envelope = self._load_envelope(connection, envelope_id)
                if envelope.state == "cancelled":
                    raise DelegationError("authorization-cancelled")
                if envelope.state == "expired":
                    raise DelegationError("authorization-expired")
                if target_host not in envelope.target_hosts:
                    raise DelegationError("target-host: new user decision required")
                if project != envelope.project_root:
                    raise DelegationError("project-scope: new user decision required")
                if baseline != envelope.baseline:
                    raise DelegationError("baseline-scope: new user decision required")
                if not _permission_within(envelope.permission_intent, permission_intent):
                    raise DelegationError("permission-intent: new user decision required")
                if envelope.horizon == "strict" and confirmed is not True:
                    raise DelegationError("strict-launch-confirmation")
                existing = connection.execute(
                    "SELECT * FROM delegations WHERE launch_key = ?", (launch_key,)
                ).fetchone()
                if existing is not None:
                    if (existing["envelope_id"] != envelope_id
                            or existing["target_host"] != target_host
                            or existing["permission_intent"] != permission_intent
                            or existing["friendly_name"] != selected_name):
                        raise DelegationError("launch-idempotency-conflict")
                    connection.execute("COMMIT")
                    return self._claim(existing)
                count = connection.execute(
                    "SELECT COUNT(*) FROM delegations WHERE envelope_id = ?", (envelope_id,)
                ).fetchone()[0]
                if count >= envelope.max_sessions:
                    raise DelegationError("session-limit: new user decision required")
                current = int(self._now())
                delegation_id = str(uuid4())
                connection.execute(
                    """INSERT INTO delegations (
                        delegation_id, envelope_id, launch_key, target_host, permission_intent,
                        friendly_name, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'creating', ?, ?)""",
                    (delegation_id, envelope_id, launch_key, target_host,
                     permission_intent, selected_name, current, current),
                )
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def count_delegations(self, envelope_id: str) -> int:
        with self._connection() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM delegations WHERE envelope_id = ?", (envelope_id,)
            ).fetchone()[0])

    def list_delegations(self) -> tuple[DelegationClaim, ...]:
        with self._connection() as connection:
            return tuple(self._claim(row) for row in connection.execute(
                "SELECT * FROM delegations ORDER BY created_at, delegation_id"
            ))

    def get_delegation(self, delegation_id: str) -> DelegationClaim:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
            ).fetchone()
            if row is None:
                raise DelegationError("delegation-not-found")
            return self._claim(row)

    @staticmethod
    def _validated_host_value(value: str, label: str) -> str:
        if not _valid_text(value, maximum=512):
            raise DelegationError(label)
        return value

    def bind_host(
        self, delegation_id: str, host_ref: str, host_session_ref: str,
        host_version: str, actual_permission: str,
    ) -> DelegationClaim:
        values = (
            self._validated_host_value(host_ref, "host-ref"),
            self._validated_host_value(host_session_ref, "host-session-ref"),
            self._validated_host_value(host_version, "host-version"),
            self._validated_host_value(actual_permission, "actual-permission"),
        )
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                if row is None:
                    raise DelegationError("delegation-not-found")
                existing = tuple(row[key] for key in
                                 ("host_ref", "host_session_ref", "host_version",
                                  "actual_permission"))
                if any(current is not None and current != requested
                       for current, requested in zip(existing, values)):
                    raise DelegationError("host-binding-conflict")
                if row["state"] not in ("creating", "unknown", "created"):
                    raise DelegationError("invalid-state-transition")
                connection.execute(
                    """UPDATE delegations SET host_ref = ?, host_session_ref = ?,
                       host_version = ?, actual_permission = ?, state = 'created',
                       updated_at = ? WHERE delegation_id = ?""",
                    (*values, int(self._now()), delegation_id),
                )
                updated = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(updated)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def record_host_unknown(self, delegation_id: str,
                            host_ref: str | None = None) -> DelegationClaim:
        if host_ref is not None:
            self._validated_host_value(host_ref, "host-ref")
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                if row is None:
                    raise DelegationError("delegation-not-found")
                if row["host_ref"] is not None and host_ref not in (None, row["host_ref"]):
                    raise DelegationError("host-binding-conflict")
                if row["state"] not in ("creating", "unknown"):
                    raise DelegationError("invalid-state-transition")
                connection.execute(
                    "UPDATE delegations SET host_ref = COALESCE(host_ref, ?), "
                    "state = 'unknown', updated_at = ? WHERE delegation_id = ?",
                    (host_ref, int(self._now()), delegation_id),
                )
                updated = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(updated)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def set_turn_ref(self, delegation_id: str, turn_ref: str) -> DelegationClaim:
        self._validated_host_value(turn_ref, "turn-ref")
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                if row is None:
                    raise DelegationError("delegation-not-found")
                if row["host_ref"] is None:
                    raise DelegationError("host-binding-required")
                if row["last_turn_ref"] not in (None, turn_ref):
                    raise DelegationError("turn-binding-conflict")
                connection.execute(
                    "UPDATE delegations SET last_turn_ref = ?, updated_at = ? "
                    "WHERE delegation_id = ?",
                    (turn_ref, int(self._now()), delegation_id),
                )
                updated = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(updated)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def begin_follow_up(self, delegation_id: str, turn_ref: str) -> DelegationClaim:
        self._validated_host_value(turn_ref, "turn-ref")
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                if row is None:
                    raise DelegationError("delegation-not-found")
                envelope = self._load_envelope(connection, row["envelope_id"])
                if envelope.state == "cancelled":
                    raise DelegationError("authorization-cancelled")
                if envelope.state == "expired":
                    raise DelegationError("authorization-expired")
                if row["state"] != "completed" or row["host_ref"] is None:
                    raise DelegationError("invalid-state-transition")
                connection.execute(
                    "UPDATE delegations SET state = 'running', last_turn_ref = ?, "
                    "updated_at = ? WHERE delegation_id = ?",
                    (turn_ref, int(self._now()), delegation_id),
                )
                updated = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(updated)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def advance(self, delegation_id: str, new_state: str, evidence: str) -> DelegationClaim:
        if (not isinstance(new_state, str) or new_state not in DELEGATION_STATES
                or new_state == "creating"):
            raise DelegationError("delegation-state")
        if _STATE_EVIDENCE.get(new_state) != evidence:
            raise DelegationError("untrusted-state-evidence")
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                if row is None:
                    raise DelegationError("delegation-not-found")
                if new_state not in _TRANSITIONS[row["state"]]:
                    raise DelegationError("invalid-state-transition")
                if new_state == "created":
                    raise DelegationError("host-binding-required")
                if (new_state in ("registered", "running", "completed")
                        and row["host_ref"] is None):
                    raise DelegationError("host-binding-required")
                if new_state in ("running", "completed") and row["last_turn_ref"] is None:
                    raise DelegationError("turn-binding-required")
                connection.execute(
                    "UPDATE delegations SET state = ?, updated_at = ? WHERE delegation_id = ?",
                    (new_state, int(self._now()), delegation_id),
                )
                updated = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._claim(updated)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def cancel_authorization(self, envelope_id: str) -> AuthorizationEnvelope:
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                envelope = self._load_envelope(connection, envelope_id)
                if envelope.state == "expired":
                    raise DelegationError("authorization-expired")
                if envelope.state != "cancelled":
                    connection.execute(
                        "UPDATE authorizations SET state = 'cancelled', updated_at = ? "
                        "WHERE envelope_id = ?",
                        (int(self._now()), envelope_id),
                    )
                row = connection.execute(
                    "SELECT * FROM authorizations WHERE envelope_id = ?", (envelope_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._envelope(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
