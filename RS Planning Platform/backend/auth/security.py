"""Password hashing and session-cookie helpers.

Uses the `bcrypt` library directly rather than passlib's CryptContext —
passlib 1.7.4 (its last release, unmaintained) breaks against bcrypt>=4.1's
API (it probes `bcrypt.__about__`, removed upstream), so passlib is not used
here despite being the more commonly-reached-for wrapper."""
import bcrypt


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
