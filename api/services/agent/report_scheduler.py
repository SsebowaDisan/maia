from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Literal

from api.schemas import ChatRequest
from api.services.agent.audit import get_audit_logger
from api.services.agent.orchestrator import get_orchestrator
from api.services.settings_service import load_user_settings
from api.context import get_context


ScheduleFrequency = Literal["daily", "weekly", "monthly"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _storage_path() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "schedules.json"


def _next_run_from(frequency: ScheduleFrequency, base: datetime) -> datetime:
    if frequency == "daily":
        return base + timedelta(days=1)
    if frequency == "weekly":
        return base + timedelta(days=7)
    return base + timedelta(days=30)


@dataclass
class ReportSchedule:
    id: str
    user_id: str
    name: str
    prompt: str
    frequency: ScheduleFrequency
    enabled: bool
    next_run_at: str
    last_run_at: str | None
    outputs: list[str]
    channels: list[str]
    date_created: str
    date_updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "prompt": self.prompt,
            "frequency": self.frequency,
            "enabled": self.enabled,
            "next_run_at": self.next_run_at,
            "last_run_at": self.last_run_at,
            "outputs": self.outputs,
            "channels": self.channels,
            "date_created": self.date_created,
            "date_updated": self.date_updated,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReportSchedule":
        return cls(
            id=str(payload.get("id") or ""),
            user_id=str(payload.get("user_id") or "default"),
            name=str(payload.get("name") or "Schedule"),
            prompt=str(payload.get("prompt") or ""),
            frequency=str(payload.get("frequency") or "weekly"),  # type: ignore[arg-type]
            enabled=bool(payload.get("enabled", True)),
            next_run_at=str(payload.get("next_run_at") or _iso(_utc_now())),
            last_run_at=payload.get("last_run_at"),
            outputs=list(payload.get("outputs") or []),
            channels=list(payload.get("channels") or []),
            date_created=str(payload.get("date_created") or _iso(_utc_now())),
            date_updated=str(payload.get("date_updated") or _iso(_utc_now())),
        )


class ReportSchedulerService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._path = _storage_path()
        self._stop_event = Event()
        self._thread: Thread | None = None
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._loop, daemon=True, name="maia-report-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.5)

    def _load(self) -> list[ReportSchedule]:
        try:
            rows = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []
        return [ReportSchedule.from_dict(item) for item in rows if isinstance(item, dict)]

    def _save(self, rows: list[ReportSchedule]) -> None:
        self._path.write_text(
            json.dumps([item.to_dict() for item in rows], indent=2),
            encoding="utf-8",
        )

    def list(self, user_id: str) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self._load() if row.user_id == user_id]

    def create(
        self,
        *,
        user_id: str,
        name: str,
        prompt: str,
        frequency: ScheduleFrequency,
        outputs: list[str],
        channels: list[str],
    ) -> dict[str, Any]:
        now = _utc_now()
        schedule = ReportSchedule(
            id=f"sched_{now.strftime('%Y%m%d%H%M%S%f')}",
            user_id=user_id,
            name=name.strip() or "Scheduled report",
            prompt=prompt.strip(),
            frequency=frequency,
            enabled=True,
            next_run_at=_iso(_next_run_from(frequency, now)),
            last_run_at=None,
            outputs=outputs,
            channels=channels,
            date_created=_iso(now),
            date_updated=_iso(now),
        )
        with self._lock:
            rows = self._load()
            rows.append(schedule)
            self._save(rows)
        return schedule.to_dict()

    def delete(self, user_id: str, schedule_id: str) -> None:
        with self._lock:
            rows = self._load()
            before = len(rows)
            rows = [row for row in rows if not (row.user_id == user_id and row.id == schedule_id)]
            if len(rows) == before:
                raise KeyError("Schedule not found")
            self._save(rows)

    def toggle(self, user_id: str, schedule_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            rows = self._load()
            for idx, row in enumerate(rows):
                if row.user_id == user_id and row.id == schedule_id:
                    row.enabled = enabled
                    row.date_updated = _iso(_utc_now())
                    rows[idx] = row
                    self._save(rows)
                    return row.to_dict()
        raise KeyError("Schedule not found")

    def trigger_now(self, user_id: str, schedule_id: str) -> dict[str, Any]:
        with self._lock:
            rows = self._load()
            target = next((row for row in rows if row.user_id == user_id and row.id == schedule_id), None)
            if target is None:
                raise KeyError("Schedule not found")
        self._execute_schedule(target)
        return {"status": "triggered", "schedule_id": schedule_id}

    def _loop(self) -> None:
        while not self._stop_event.wait(20):
            due: list[ReportSchedule] = []
            with self._lock:
                rows = self._load()
                now = _utc_now()
                for row in rows:
                    next_run = _parse(row.next_run_at)
                    if not row.enabled or next_run is None:
                        continue
                    if next_run <= now:
                        due.append(row)
                if not due:
                    continue
                for row in due:
                    row.last_run_at = _iso(now)
                    row.next_run_at = _iso(_next_run_from(row.frequency, now))
                    row.date_updated = _iso(now)
                self._save(rows)
            for schedule in due:
                self._execute_schedule(schedule)

    def _execute_schedule(self, schedule: ReportSchedule) -> None:
        settings = load_user_settings(get_context(), schedule.user_id)
        request = ChatRequest(
            message=schedule.prompt,
            agent_mode="company_agent",
            agent_goal=f"Scheduled report: {schedule.name}",
        )
        orchestrator = get_orchestrator()
        iterator = orchestrator.run_stream(
            user_id=schedule.user_id,
            conversation_id=f"scheduled:{schedule.id}",
            request=request,
            settings=settings,
        )
        try:
            while True:
                next(iterator)
        except StopIteration as stop:
            result = stop.value
            get_audit_logger().write(
                user_id=schedule.user_id,
                tenant_id=str(settings.get("agent.tenant_id") or schedule.user_id),
                run_id=result.run_id,
                event="scheduled_report_completed",
                payload={
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "output_channels": schedule.channels,
                },
            )


_scheduler: ReportSchedulerService | None = None


def get_report_scheduler() -> ReportSchedulerService:
    global _scheduler
    if _scheduler is None:
        _scheduler = ReportSchedulerService()
    return _scheduler
