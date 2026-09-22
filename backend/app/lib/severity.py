_MAP = {
    "warning": "warn",
    "error": "err",
    "information": "info",
    "critical": "crit",
}


def normalize_severity(raw: str) -> str:
    return _MAP.get(raw.lower(), raw.lower())
