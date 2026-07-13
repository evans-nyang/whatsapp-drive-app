import sys

from loguru import logger

from app.config import get_settings


def configure_logging(service_name: str) -> None:
    """
    Configure Loguru to emit structured JSON to stdout, tagged with the
    originating service. Cloud log aggregators (Cloud Logging, CloudWatch,
    etc.) pick this up directly — no file sinks, since containers are
    stateless and ephemeral.
    """
    settings = get_settings()

    logger.remove()  # drop the default handler
    logger.configure(extra={"service": service_name})
    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=True,  # JSON output
        backtrace=False,
        diagnose=settings.environment != "production",
    )
