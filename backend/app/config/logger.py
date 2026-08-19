"""Minimal application logger.

Provides a single shared ``logger`` used for server-side logging of
unexpected errors. Errors are logged with full detail on the server while
clients only ever receive safe, generic messages (see ``app.core.exception``).
"""

import logging

logger = logging.getLogger("app")

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    # Avoid duplicate log lines if the root logger also has handlers.
    logger.propagate = False
