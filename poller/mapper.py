"""
Map SD-LAN API responses onto the cloud dashboard's ingest messages.

The cloud contract (backend/app/schemas/ingest.py) takes three message kinds:

    edge_health   this poller's own heartbeat
    periodic      routine device health sample
    transition    device crossed a health threshold -> opens/resolves an alert

Unlike the syslog agent, health here is READ, not inferred. The platform tells
us `lost_contact`, `PSU1`, `Fan1`, `Temp1` and per-port `port_status` directly,
so a device being down is a fact rather than a guess about silence.

Scores are on the same 0-100 scale the syslog agent uses so both sources look
alike on the dashboard.
"""
import time

# Status ranking, worst first, so a device takes its worst finding.
_RANK = {"unhealthy": 0, "degraded": 1, "healthy": 2, "unknown": 3}

_BAD_HW = {"fail", "failed", "bad", "missing", "absent", "error", "critical"}
_OK_HW = {"ok", "good", "normal", "present", "true"}


def _worst(a, b):
    return a if _RANK.get(a, 3) <= _RANK.get(b, 3) else b


def _num(v):
    """Best-effort float; the API mixes strings and numbers."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().rstrip("Cc").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _hw_state(v):
    """Normalise a PSU/Fan style value to 'ok' | 'bad' | 'unknown'."""
    if v is None:
        return "unknown"
    if isinstance(v, bool):
        return "ok" if v else "bad"
    s = str(v).strip().lower()
    if not s:
        return "unknown"
    if s in _OK_HW:
        return "ok"
    if s in _BAD_HW:
        return "bad"
    for bad in _BAD_HW:
        if bad in s:
            return "bad"
    return "unknown"


def _temps(device):
    """Every temperature reading on a device, from attributes or Temp arrays."""
    out = []
    attrs = device.get("attributes") or {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            if str(k).lower().startswith("temp"):
                n = _num(v)
                if n is not None:
                    out.append(n)
    t = device.get("Temp") if "Temp" in device else device.get("temp")
    if isinstance(t, list):
        out.extend(n for n in (_num(x) for x in t) if n is not None)
    else:
        n = _num(t)
        if n is not None:
            out.append(n)
    return out


def _hw_items(device):
    """(name, state) for each PSU/Fan style attribute."""
    items = []
    attrs = device.get("attributes") or {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            kl = str(k).lower()
            if kl.startswith("psu") or kl.startswith("fan") or kl.startswith("power"):
                items.append((str(k), _hw_state(v)))
    # status query's switch_status carries a bare PSU field
    if "PSU" in device:
        items.append(("PSU", _hw_state(device.get("PSU"))))
    return items


def device_id_for(cfg, device):
    """The cloud device_id for an SD-LAN device record."""
    source = cfg.get("device_id_source", "dev_id")
    raw = device.get(source)
    if raw in (None, ""):
        for fallback in ("dev_id", "hw_sn", "hw_ident", "endpoint_name", "hw_hostname"):
            raw = device.get(fallback)
            if raw not in (None, ""):
                break
    if raw in (None, ""):
        return None
    slug = str(raw).strip().replace(" ", "_").replace("/", "-").replace(":", "")
    prefix = (cfg.get("device_id_prefix") or "").strip()
    return f"{prefix}-{slug}" if prefix else slug


def _device_class(cfg, device):
    model = " ".join(str(device.get(k, "")) for k in ("hw_model", "hw_mfg")).lower()
    if device.get("is_tor") in (True, "True", "true", 1):
        return "tor_switch"
    for needle, klass in (("poe", "poe_switch"), ("switch", "switch"),
                          ("router", "router"), ("ont", "optical_edge"),
                          ("ftth", "optical_edge"), ("fttp", "optical_edge")):
        if needle in model:
            return klass
    return cfg.get("default_device_class", "switch")


def _ports(device):
    """
    Per-port records from a networks device entry.

    The tech pub nests `connections` as {port_number: {...}}; tolerate a list.
    """
    conns = device.get("connections")
    if isinstance(conns, dict):
        for port, rec in conns.items():
            if isinstance(rec, dict):
                yield str(port), rec
    elif isinstance(conns, list):
        for rec in conns:
            if isinstance(rec, dict):
                yield str(rec.get("Port Number", rec.get("port", "?"))), rec


def assess_device(cfg, device, now=None):
    """
    Read a device's health from the API record.

    Returns (status, score, reasons, metrics) where metrics matches the
    cloud DeviceMetrics shape (event_count / error_count / warn_count).
    """
    now = now or time.time()
    status, score, reasons = "healthy", 100, []
    errors = warns = 0

    # --- out of contact: the platform states this outright ---------------
    lost = device.get("lost_contact")
    in_contact = True
    if lost not in (None, "", "null", 0, "0"):
        in_contact = False
    state = device.get(".state", device.get("state"))
    if state in (False, "False", "false", 0):
        in_contact = False

    if not in_contact:
        reason = "lost_contact"
        why = device.get("lost_reason")
        if why:
            reason = f"lost_contact:{str(why)[:60]}"
        return "unhealthy", 0, [reason], {
            "event_count": 1, "error_count": 1, "warn_count": 0}

    # --- hardware: PSU / fan ---------------------------------------------
    for name, st in _hw_items(device):
        if st == "bad":
            status = _worst(status, "unhealthy")
            score -= 40
            errors += 1
            reasons.append(f"hardware_fault:{name}")

    # --- thermal ----------------------------------------------------------
    temps = _temps(device)
    if temps:
        hottest = max(temps)
        if hottest >= cfg.get("temp_crit_celsius", 70.0):
            status = _worst(status, "unhealthy")
            score -= 35
            errors += 1
            reasons.append(f"thermal_critical:{hottest:.0f}C")
        elif hottest >= cfg.get("temp_warn_celsius", 55.0):
            status = _worst(status, "degraded")
            score -= 15
            warns += 1
            reasons.append(f"thermal_warning:{hottest:.0f}C")

    # --- ports ------------------------------------------------------------
    down = []
    flapping = []
    weak_optics = []
    flap_window = cfg.get("link_flap_window_seconds", 900)
    rx_warn = cfg.get("optical_rx_warn_dbm", -20.0)

    for port, rec in _ports(device):
        pstatus = str(rec.get("port_status", "")).strip().lower()
        if pstatus in ("down", "inactive", "false"):
            down.append(port)
        last_change = _num(rec.get("last_link_change"))
        if last_change is not None and 0 < (now - last_change) < flap_window:
            flapping.append(port)
        rx = _num(rec.get("rx_optical_level"))
        if rx is not None and rx < rx_warn and str(rec.get("sfp_type", "")).lower() != "copper":
            weak_optics.append((port, rx))

    if down:
        status = _worst(status, "degraded")
        score -= min(len(down) * 5, 25)
        warns += len(down)
        reasons.append(f"ports_down:{len(down)}")
    if len(flapping) >= cfg.get("link_flap_min_changes", 3):
        status = _worst(status, "degraded")
        score -= 15
        warns += 1
        reasons.append(f"link_flap:{len(flapping)}_ports")
    if weak_optics:
        status = _worst(status, "degraded")
        score -= min(len(weak_optics) * 5, 20)
        warns += len(weak_optics)
        worst_rx = min(r for _p, r in weak_optics)
        reasons.append(f"optical_low:{len(weak_optics)}_ports_min_{worst_rx:.1f}dBm")

    score = max(0, min(100, score))
    if status == "healthy" and score < 85:
        status = "degraded"
    metrics = {
        "event_count": max(1, errors + warns),
        "error_count": errors,
        "warn_count": warns,
    }
    return status, score, reasons, metrics


def device_message(cfg, device, domain, site, kind="periodic", now=None):
    """Build a periodic or transition message for one SD-LAN device."""
    now = now or time.time()
    dev_id = device_id_for(cfg, device)
    if dev_id is None:
        return None

    status, score, reasons, metrics = assess_device(cfg, device, now)

    name = (device.get("endpoint_name") or device.get("hw_hostname")
            or device.get("hw_ident") or dev_id)
    resolved_site = site or device.get("Site") or domain or "unknown"

    override = (cfg.get("device_overrides") or {}).get(dev_id, {})

    msg = {
        "kind": kind,
        "ts": now,
        "device_id": dev_id,
        "device_name": override.get("device_name") or str(name)[:120],
        "device_class": override.get("device_class") or _device_class(cfg, device),
        "vendor": override.get("vendor") or str(device.get("hw_mfg") or "unknown")[:60],
        "site": str(override.get("site") or resolved_site)[:120],
        "health": {"status": status, "score": score, "reasons": reasons[:10]},
        "metrics": metrics,
    }

    if kind == "transition":
        msg["top_events"] = _top_events(device, reasons, now)
    return msg


def _top_events(device, reasons, now):
    """
    Synthesise top_events from the API's structured state.

    The cloud alert view renders these as the causal chain, so each reason
    becomes one event with the severity the backend expects.
    """
    events = []
    for r in reasons[:5]:
        if r.startswith("lost_contact"):
            sev, cat = "crit", "availability"
        elif r.startswith("hardware_fault"):
            sev, cat = "err", "hardware"
        elif r.startswith("thermal_critical"):
            sev, cat = "err", "thermal"
        elif r.startswith("thermal_warning"):
            sev, cat = "warning", "thermal"
        elif r.startswith("ports_down") or r.startswith("link_flap"):
            sev, cat = "warning", "link"
        elif r.startswith("optical_low"):
            sev, cat = "warning", "optical"
        else:
            sev, cat = "warning", "other"
        detail = device.get("hw_hostname") or device.get("endpoint_name") or ""
        events.append({
            "ts": now,
            "severity": sev,
            "category": cat,
            "message": f"{r}{(' on ' + str(detail)) if detail else ''}"[:200],
        })
    if not events:
        events.append({"ts": now, "severity": "info", "category": "other",
                       "message": "health returned to normal"})
    return events


# ------------------------------------------------------------ the platform

def assess_platform(cfg, status_response, problems, now=None):
    """Health of the orchestration platform itself."""
    now = now or time.time()
    status, score, reasons = "healthy", 100, []
    errors = warns = 0

    lost = _num(status_response.get("fttp_lost_contact"))
    if lost and lost > 0:
        status = _worst(status, "degraded")
        score -= min(int(lost) * 5, 30)
        warns += int(lost)
        reasons.append(f"optical_edge_out_of_contact:{int(lost)}")

    rebooted = _num(status_response.get("fttp_rebooted"))
    if rebooted and rebooted > 0:
        reasons.append(f"optical_edge_rebooted_24h:{int(rebooted)}")
        warns += int(rebooted)
        status = _worst(status, "degraded")
        score -= 5

    free = _num(status_response.get("freespace"))
    if free is not None and free < cfg.get("platform_freespace_warn_percent", 15.0):
        status = _worst(status, "degraded")
        score -= 20
        warns += 1
        reasons.append(f"platform_disk_low:{free:.0f}pct_free")

    buffer_state = str(status_response.get("bufferwatch") or "").strip().lower()
    if buffer_state and buffer_state not in ("normal", "starting", ""):
        status = _worst(status, "degraded")
        score -= 15
        warns += 1
        reasons.append(f"bufferwatch:{buffer_state[:40]}")

    lic = status_response.get("tenant_licenses")
    if isinstance(lic, dict):
        if lic.get("expired") in (True, "TRUE", "true"):
            status = _worst(status, "unhealthy")
            score -= 50
            errors += 1
            reasons.append("license_expired")
        if lic.get("missing") in (True, "TRUE", "true"):
            status = _worst(status, "unhealthy")
            score -= 30
            errors += 1
            reasons.append("license_file_missing")
        elif lic.get("valid") in (False, "FALSE", "false"):
            status = _worst(status, "degraded")
            score -= 20
            warns += 1
            reasons.append("license_invalid")
        not_after = _num(lic.get("not_after"))
        if not_after and 0 < (not_after - now) < 30 * 86400:
            days = int((not_after - now) / 86400)
            status = _worst(status, "degraded")
            score -= 10
            warns += 1
            reasons.append(f"license_expires_in_{days}d")

    if problems:
        status = _worst(status, "degraded")
        score -= min(len(problems) * 10, 40)
        errors += len(problems)
        reasons.append(f"active_problems:{len(problems)}")

    score = max(0, min(100, score))
    if status == "healthy" and score < 85:
        status = "degraded"
    return status, score, reasons, {
        "event_count": max(1, errors + warns),
        "error_count": errors,
        "warn_count": warns,
    }


def platform_message(cfg, status_response, problems, kind="periodic", now=None):
    """Build a message representing the orchestration platform as a device."""
    now = now or time.time()
    status, score, reasons, metrics = assess_platform(cfg, status_response, problems, now)
    prefix = (cfg.get("device_id_prefix") or "sdlan").strip()
    msg = {
        "kind": kind,
        "ts": now,
        "device_id": f"{prefix}-platform",
        "device_name": str(status_response.get("hostname") or "sdlan_platform")[:120],
        "device_class": cfg.get("platform_device_class", "orchestrator"),
        "vendor": "corning",
        "site": str(cfg.get("property_name") or "unknown")[:120],
        "health": {"status": status, "score": score, "reasons": reasons[:10]},
        "metrics": metrics,
    }
    if kind == "transition":
        events = []
        for p in problems[:5]:
            events.append({
                "ts": now,
                "severity": "err",
                "category": "platform",
                "message": (f"{p.get('element_name') or p.get('element') or 'element'}: "
                            f"{p.get('message') or 'problem reported'}")[:200],
            })
        for r in reasons[:5 - len(events)]:
            events.append({"ts": now, "severity": "warning",
                           "category": "platform", "message": r[:200]})
        if not events:
            events.append({"ts": now, "severity": "info", "category": "platform",
                           "message": "platform returned to normal"})
        msg["top_events"] = events
    return msg


def edge_health_message(cfg, tracked, unhealthy, queue_depth, now=None):
    """This poller's own heartbeat - populates the cloud edge_boxes table."""
    return {
        "kind": "edge_health",
        "ts": now or time.time(),
        "metrics": {
            "tracked_devices": int(tracked),
            "unhealthy_devices": int(unhealthy),
            "queue_depth": int(queue_depth),
            "summary_interval_seconds": int(cfg.get("poll_interval_seconds", 300)),
        },
    }
