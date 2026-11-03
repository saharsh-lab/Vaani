import re


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str | None) -> str:
    """Return the number in E.164 form. A bare 10-digit number is taken as Indian."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        number = digits
    elif len(digits) == 10:
        number = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        number = "91" + digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        number = digits
    else:
        raise InvalidPhone(raw)
    if not 8 <= len(number) <= 15:
        raise InvalidPhone(raw)
    return "+" + number


def mask_phone(phone: str | None) -> str:
    """For logs: +919876543210 -> +91******3210."""
    if not phone:
        return "-"
    if len(phone) <= 7:
        return "*" * len(phone)
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
