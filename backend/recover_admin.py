from datetime import datetime
from getpass import getpass

from app.auth import hash_password
from app.database import SessionLocal
from app import models as m

password = getpass("New administrator password: ")
confirm = getpass("Confirm administrator password: ")

if len(password) < 12:
    raise SystemExit("Password must be at least 12 characters.")
if password != confirm:
    raise SystemExit("Passwords do not match.")

with SessionLocal.begin() as db:
    target = (
        db.query(m.User)
        .filter_by(username="<admin-username>", role="admin")
        .one()
    )

    conflict = (
        db.query(m.User)
        .filter(m.User.username == "admin", m.User.id != target.id)
        .count()
    )

    if conflict:
        raise SystemExit("Admin username already exists. Recovery aborted.")

    target.username = "admin"
    target.password_hash = hash_password(password)

    for session in db.query(m.AuthSession).filter_by(user_id=target.id).all():
        session.revoked_at = datetime.utcnow()

print("Administrator recovery completed successfully.")
