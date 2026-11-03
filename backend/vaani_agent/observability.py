"""Error reporting (Sentry), shared by the API and the voice worker.

Off unless SENTRY_DSN is set. Request bodies and personal data are never sent:
they contain customers' phone numbers and what they said.
"""

import logging
import os

log = logging.getLogger(__name__)


def init_sentry(component: str) -> bool:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "development"),
        server_name=component,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
    )
    log.info("Sentry enabled for %s", component)
    return True
