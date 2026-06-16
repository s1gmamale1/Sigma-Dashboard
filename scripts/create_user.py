"""Create (or update) a dashboard login account from the command line.

Usage:
    python scripts/create_user.py <username> <display_name> <role> <temp_password> [--no-force-change]

Roles: admin | manager | viewer. By default the account must change its password
on first login (drop that with --no-force-change). Targets whatever database the
app config resolves — set SIGMA_DATABASE_URL to point at a specific .db file:

    SIGMA_DATABASE_URL=sqlite:///./dashboard.preview.db \
        python scripts/create_user.py cody Cody manager 159075
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth import hash_password
from backend.app.bootstrap import init_db
from backend.app.db import engine
from backend.app.models import USER_ROLES, User


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--no-force-change"]
    force_change = "--no-force-change" not in sys.argv[1:]
    if len(args) != 4:
        raise SystemExit(
            "usage: create_user.py <username> <display_name> <role> <temp_password> [--no-force-change]"
        )
    username, display_name, role, temp_password = args
    if role not in USER_ROLES:
        raise SystemExit(f"role must be one of {USER_ROLES}, got {role!r}")

    init_db()  # ensure schema exists (and the env admin is seeded) before we add anyone
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username)
            db.add(user)
            verb = "created"
        else:
            verb = "updated"
        user.display_name = display_name
        user.role = role
        user.password_hash = hash_password(temp_password)
        user.active = True
        user.must_change_password = force_change
        db.commit()
        print(
            f"{verb} user {username!r} (role={role}, "
            f"must_change_password={force_change})"
        )


if __name__ == "__main__":
    main()
