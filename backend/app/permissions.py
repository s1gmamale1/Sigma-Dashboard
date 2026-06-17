"""Role → permission mapping for dashboard users.

Three roles are defined (see `models.USER_ROLES`):
- **admin**   — full read/write on every area, including user management.
- **manager** — full read/write on all data areas, but no user management.
- **viewer**  — read-only on all data areas, no user management.

The backend enforces access in tiers (view / edit / admin — see `auth.py`); this
module is the single source of truth for *which area maps to what*, and it feeds
the `/auth/me` payload the frontend uses to gate navigation and controls.
"""

from .models import USER_ROLES

# Every guardable surface in the app. `users` is the admin-only management area.
DATA_AREAS = ("attendance", "reports", "performance", "goals", "projects", "sheets")
AREAS = (*DATA_AREAS, "users")
ACTIONS = ("read", "write")

ROLE_PERMISSIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "admin": {area: ("read", "write") for area in AREAS},
    "manager": {area: ("read", "write") for area in DATA_AREAS},
    "viewer": {area: ("read",) for area in DATA_AREAS},
}


def has_permission(role: str, area: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role, {}).get(area, ())


def can_write(role: str) -> bool:
    """True if the role can write *anything* — i.e. it is not a read-only role."""
    return any("write" in actions for actions in ROLE_PERMISSIONS.get(role, {}).values())


def permissions_for(role: str) -> dict[str, list[str]]:
    """Serializable permission map for the `/auth/me` response."""
    return {area: list(actions) for area, actions in ROLE_PERMISSIONS.get(role, {}).items()}


__all__ = ["USER_ROLES", "DATA_AREAS", "AREAS", "ACTIONS", "ROLE_PERMISSIONS", "has_permission", "can_write", "permissions_for"]
