from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config.logger import logger


def register_exception_handlers(app: FastAPI):

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception,
    ):
        # Log the FULL exception (type, message, traceback) server-side only.
        # This never reaches the client.
        logger.exception(
            "Unhandled exception during %s %s",
            request.method,
            request.url.path,
        )

        # Return a safe, generic message. Do NOT leak str(exc), which could
        # expose Mongo errors, filesystem paths, driver internals, secrets,
        # or stack details.
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
