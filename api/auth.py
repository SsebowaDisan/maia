from typing import Annotated

from fastapi import Header


def get_current_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    return "default"

