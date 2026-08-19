"""Shared pytest setup for the backend test-suite.

Makes ``app`` importable and provides dummy values for the *required* settings
fields so importing modules that pull in ``app.config.settings`` (e.g. the text
extraction service) never needs a real ``.env``, MongoDB, or Groq.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Required Settings fields — set only if absent so a real environment wins.
_DUMMY_ENV = {
    "APP_NAME": "test-app",
    "APP_VERSION": "0.0.0-test",
    "MONGODB_URI": "mongodb://localhost:27017",
    "DATABASE_NAME": "test_db",
    "JWT_SECRET_KEY": "test-secret",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "GROQ_API_KEY": "test-groq-key",
}

for _key, _value in _DUMMY_ENV.items():
    os.environ.setdefault(_key, _value)
