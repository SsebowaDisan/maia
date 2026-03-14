import datetime
import uuid

import ktem.db.base_models as base_models
from ktem.db.engine import engine
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel
from theflow.settings import settings
from theflow.utils.modules import import_dotted_string
from tzlocal import get_localzone

_base_conv = (
    import_dotted_string(settings.KH_TABLE_CONV, safe=False)
    if hasattr(settings, "KH_TABLE_CONV")
    else base_models.BaseConversation
)

_base_user = (
    import_dotted_string(settings.KH_TABLE_USER, safe=False)
    if hasattr(settings, "KH_TABLE_USER")
    else base_models.BaseUser
)

_base_settings = (
    import_dotted_string(settings.KH_TABLE_SETTINGS, safe=False)
    if hasattr(settings, "KH_TABLE_SETTINGS")
    else base_models.BaseSettings
)

_base_issue_report = (
    import_dotted_string(settings.KH_TABLE_ISSUE_REPORT, safe=False)
    if hasattr(settings, "KH_TABLE_ISSUE_REPORT")
    else base_models.BaseIssueReport
)


class Conversation(_base_conv, table=True):  # type: ignore
    """Conversation record"""


class User(_base_user, table=True):  # type: ignore
    """User table"""


class Settings(_base_settings, table=True):  # type: ignore
    """Record of settings"""


class IssueReport(_base_issue_report, table=True):  # type: ignore
    """Record of issues"""


class ComputerUseSessionRecord(SQLModel, table=True):
    """Persistent metadata for a Computer Use browser session.

    The actual Playwright browser process is in-memory and lost on server
    restart.  This table keeps a lightweight record so the frontend can
    list sessions and the backend can detect stale (unclean-shutdown) ones.
    """

    __table_args__ = {"extend_existing": True}

    session_id: str = Field(primary_key=True)
    user_id: str = Field(default="", index=True)
    start_url: str = Field(default="")
    status: str = Field(default="active")  # active | closed | stale
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    date_closed: datetime.datetime | None = Field(default=None)


class MindmapShare(SQLModel, table=True):
    """Shared mind-map payload for cross-user links."""

    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    share_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:16], index=True, unique=True
    )
    conversation_id: str = Field(default="", index=True)
    user: str = Field(default="", index=True)
    title: str = Field(default="Mind-map")
    payload: dict = Field(default={}, sa_column=Column(JSON))
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    date_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )


if not getattr(settings, "KH_ENABLE_ALEMBIC", False):
    SQLModel.metadata.create_all(engine)
