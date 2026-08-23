"""One-time user creation. Run: python seed_admin.py"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this backend/, for auth.security
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Tentative AOP Forecaster"))

from auth.security import hash_password  # noqa: E402
from db.base import SessionLocal  # noqa: E402
from db.models.auth import ROLES, User  # noqa: E402


def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    role = input(f"Role ({'/'.join(ROLES)}) [planner]: ").strip() or "planner"
    if role not in ROLES:
        print(f"Invalid role '{role}', must be one of {ROLES}")
        return
    is_admin = (input("Grant admin (user management) access? [y/N]: ").strip().lower() == "y")
    session = SessionLocal()
    try:
        session.add(User(username=username, password_hash=hash_password(password), role=role, is_admin=is_admin))
        session.commit()
        print(f"Created user '{username}' — role={role}, is_admin={is_admin}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
