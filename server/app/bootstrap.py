"""Create the owner explicitly using environment credentials, once per database."""
import os
from .db import Agency, Membership, SessionLocal, User, initialize
from .security import hasher


def bootstrap():
    email = os.environ.get("STRATA_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("STRATA_ADMIN_PASSWORD", "")
    if not email or "@" not in email or len(password) < 14:
        raise SystemExit("Set STRATA_ADMIN_EMAIL and STRATA_ADMIN_PASSWORD (minimum 14 characters)")
    initialize()
    with SessionLocal.begin() as db:
        if db.query(User).count():
            raise SystemExit("Owner exists; refusing to overwrite credentials")
        user = User(email=email, password_hash=hasher.hash(password), is_owner=True)
        agency = Agency(name="IAmStrata")
        db.add_all([user, agency])
        db.flush()
        db.add(Membership(user_id=user.id, agency_id=agency.id, role="owner"))
    print("Initial owner and IAmStrata agency created; no demo contacts were inserted.")


if __name__ == "__main__":
    bootstrap()
