"""Domain errors. The API turns them into JSON the agent can read aloud, e.g.
{"error": "slot_unavailable", "message": "...", "alternatives": [...]}."""

from typing import Any


class VaaniError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(VaaniError):
    status_code = 404
    code = "not_found"


class InvalidRequest(VaaniError):
    status_code = 422
    code = "invalid_request"


class SlotUnavailable(VaaniError):
    status_code = 409
    code = "slot_unavailable"
