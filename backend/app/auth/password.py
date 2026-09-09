import re
import bcrypt

def validate_password_strength(password: str) -> str:
    """Validate password against strong password policy:
    - At least 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter (A-Z)")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter (a-z)")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number (0-9)")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/]", password):
        raise ValueError("Password must contain at least one special character (!@#$%^&*...)")
    return password


def hash_password(password: str) -> str:
    # bcrypt requires bytes, so encode the string
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_bytes.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except ValueError:
        # Invalid hash format
        return False