import logging

from config import settings


def configure_logging() -> None:
    """Console logging setup, called once from each entry point (app.py / run_agent.py)."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
