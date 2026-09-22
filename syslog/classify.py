import re

RULES = [
    ("link",         "warning", re.compile(r"link state changed to down|interface .* down", re.I)),
    ("link",         "info",    re.compile(r"link state changed to up|interface .* up", re.I)),
    ("auth",         "error",   re.compile(r"authentication fail|login fail|invalid user", re.I)),
    ("auth",         "info",    re.compile(r"user .* logged in|accepted password", re.I)),
    ("hardware",     "error",   re.compile(r"power supply .* fault|fan fail|psu fail", re.I)),
    ("performance",  "warning", re.compile(r"cpu utilization|memory usage high|packet loss", re.I)),
    ("thermal",      "warning", re.compile(r"temperature sensor|temp.*\d+c", re.I)),
    ("routing",      "error",   re.compile(r"bgp neighbor .* (idle|down)|ospf adjacency lost", re.I)),
    ("config",       "info",    re.compile(r"configuration saved|config changed", re.I)),
]

SEVERITY_RANK = {
    "emerg": 0, "alert": 1, "crit": 2,
    "err": 3, "error": 3,
    "warning": 4, "warn": 4,
    "notice": 5, "info": 6, "debug": 7,
}


def classify(message, severity):
    for category, _floor, rx in RULES:
        if rx.search(message):
            return category
    return "other"


def is_noise(severity, category):
    rank = SEVERITY_RANK.get(severity, 6)
    if rank >= 7:
        return True
    if rank >= 6 and category == "other":
        return True
    return False
