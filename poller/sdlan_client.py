"""
Client for the Corning ONE SD-LAN Northbound Interface (JSON REST).

Built from "Corning ONE SD-LAN Technical Publication - Northbound Interface API
(JSON REST)", (c) 2022 Corning. All four documented queries are implemented:

    status          summary system info, problems list, switch_status
    networks        systemwide switching device report (per-device detail)
    device_details  MAC addresses + historical per-port statistics
    slice           endpoint traffic path to the TOR

The tech pub documents the parameters as a query string but recommends POST
"so that username/password information is protected". This client therefore
defaults to POST with the parameters in the request body, and NEVER puts
credentials in a URL it logs or raises in an exception.

UNVERIFIED AGAINST REAL HARDWARE: field names come from the tech pub, but the
exact JSON nesting (especially `problems`, `switch_status` and the Domain/Site
wrapping of `networks`) could not be checked against a live platform. Every
accessor here tolerates a missing or differently-shaped field rather than
raising, and `probe.py` dumps raw responses so the mapping can be corrected
quickly against a real system.
"""
import json
import time
from pathlib import Path

import requests

import config as poller_config


class SdLanError(Exception):
    """API call failed. Message never contains credentials."""


class SdLanClient:
    def __init__(self, cfg, session=None):
        self.cfg = cfg
        self.url = poller_config.safe_url(cfg)
        self.timeout = cfg.get("sdlan_timeout_seconds", 30)
        self.method = (cfg.get("sdlan_http_method") or "POST").upper()
        self.post_format = (cfg.get("sdlan_post_format") or "form").lower()
        self._session = session or requests.Session()
        self._raw_log = (cfg.get("sdlan_raw_log_path") or "").strip()

        verify = cfg.get("sdlan_verify_tls", True)
        ca = (cfg.get("sdlan_ca_bundle") or "").strip()
        self.verify = ca if (verify and ca) else bool(verify)

    # ---------------------------------------------------------------- core

    def _credentials(self):
        return {
            "username": self.cfg.get("sdlan_username", ""),
            "password": self.cfg.get("sdlan_password", ""),
        }

    def _request(self, params):
        """
        Issue one API call. `params` must NOT contain credentials - they are
        added here so no caller can accidentally log them.
        """
        safe_params = dict(params)           # for logs and errors
        sent = {**self._credentials(), **params}

        try:
            if self.method == "GET":
                resp = self._session.get(
                    self.url, params=sent, timeout=self.timeout, verify=self.verify)
            elif self.post_format == "json":
                resp = self._session.post(
                    self.url, json=sent, timeout=self.timeout, verify=self.verify)
            elif self.post_format == "query":
                # params in the query string, POST body empty
                resp = self._session.post(
                    self.url, params=sent, timeout=self.timeout, verify=self.verify)
            else:
                resp = self._session.post(
                    self.url, data=sent, timeout=self.timeout, verify=self.verify)
        except requests.exceptions.SSLError as e:
            raise SdLanError(
                f"TLS verification failed for {self.url}: {e}. If the platform "
                f"uses a private CA, set sdlan_ca_bundle to its certificate."
            ) from None
        except Exception as e:
            raise SdLanError(
                f"{type(e).__name__} calling {self.url} {safe_params}: {e}") from None

        if resp.status_code in (401, 403):
            raise SdLanError(
                f"HTTP {resp.status_code} from {self.url} - SD-LAN rejected the "
                f"credentials (check sdlan_username / sdlan_password)")
        if not (200 <= resp.status_code < 300):
            body = (resp.text or "")[:400]
            raise SdLanError(
                f"HTTP {resp.status_code} from {self.url} {safe_params}: {body}")

        try:
            data = resp.json()
        except ValueError:
            body = (resp.text or "")[:400]
            raise SdLanError(
                f"{self.url} {safe_params} returned non-JSON "
                f"(content-type {resp.headers.get('Content-Type')}): {body}") from None

        self._log_raw(safe_params, data)
        return data

    def _log_raw(self, params, data):
        """Append a raw response for mapping work. Credentials redacted."""
        if not self._raw_log:
            return
        try:
            block = {
                "ts": time.time(),
                "url": self.url,
                "params": poller_config.redact(params),
                "response": poller_config.redact(data),
            }
            Path(self._raw_log).parent.mkdir(parents=True, exist_ok=True)
            with open(self._raw_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(block, ensure_ascii=False, default=str) + "\n")
        except OSError as e:
            print(f"sdlan raw log write error ({self._raw_log}): {e}")

    # ------------------------------------------------------------- queries

    def status(self):
        """query=status - system summary, problems list, switch_status."""
        return self._request({"query": "status"})

    def networks(self, setname=None, site=None):
        """query=networks - systemwide switching device report."""
        params = {"query": "networks"}
        setname = setname if setname is not None else (self.cfg.get("sdlan_setname") or "")
        site = site if site is not None else (self.cfg.get("sdlan_site") or "")
        if setname:
            params["setname"] = setname
        if site:
            params["site"] = site
        return self._request(params)

    def device_details(self, dev_id=None, endpoint_id=None, endpoint_name=None,
                       start=None, stop=None):
        """
        query=device_details - MAC addresses + historical statistics.

        Exactly one of dev_id / endpoint_id / endpoint_name must be given;
        the tech pub prefers dev_id as the most efficient.
        """
        given = [x for x in (dev_id, endpoint_id, endpoint_name) if x not in (None, "")]
        if len(given) != 1:
            raise SdLanError(
                "device_details needs exactly one of dev_id, endpoint_id, endpoint_name")
        params = {"query": "device_details"}
        if dev_id not in (None, ""):
            params["dev_id"] = dev_id
        elif endpoint_id not in (None, ""):
            params["endpoint_id"] = endpoint_id
        else:
            params["endpoint_name"] = endpoint_name
        if start is not None:
            params["start"] = int(start)
        if stop is not None:
            params["stop"] = int(stop)
        return self._request(params)

    def slice_view(self, endpoint):
        """query=slice - endpoint traffic path towards the TOR."""
        return self._request({"query": "slice", "endpoint": endpoint})


# --------------------------------------------------------------- shape helpers
#
# The tech pub nests the networks report as Domain -> Site -> device records,
# but does not pin down the exact container types. These helpers walk whatever
# came back and yield (domain, site, device_dict) without assuming a shape.

DEVICE_MARKERS = ("dev_id", "hw_ident", "hw_hostname", "endpoint_name", "hw_sn")


def _looks_like_device(d):
    return isinstance(d, dict) and sum(1 for k in DEVICE_MARKERS if k in d) >= 2


def iter_devices(networks_response):
    """
    Yield (domain, site, device) for every device record in a networks
    response, regardless of how deeply it is nested or whether the containers
    are dicts keyed by name or lists.

    Domain and site are best-effort: whatever dict keys were walked through to
    reach the device, or the device's own 'Domain'/'Site' fields.
    """
    seen = set()

    def walk(node, domain, site, depth=0):
        if depth > 8:
            return
        if _looks_like_device(node):
            key = id(node)
            if key not in seen:
                seen.add(key)
                yield (node.get("Domain") or node.get("domain") or domain,
                       node.get("Site") or node.get("site") or site,
                       node)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(v, (dict, list)):
                    continue
                # A named container one level down is a domain, then a site.
                if domain is None:
                    yield from walk(v, k, site, depth + 1)
                elif site is None:
                    yield from walk(v, domain, k, depth + 1)
                else:
                    yield from walk(v, domain, site, depth + 1)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v, domain, site, depth + 1)

    yield from walk(networks_response, None, None)


def iter_problems(status_response):
    """
    Yield each entry of the status response's `problems` list as a dict.

    The tech pub lists the fields an entry "may have" (installation_name,
    tenant_id, element, tenant_name, message, element_id, element_name,
    installation_id) without fixing the container, so accept list or dict.
    """
    if not isinstance(status_response, dict):
        return
    problems = status_response.get("problems")
    if isinstance(problems, dict):
        problems = list(problems.values())
    if not isinstance(problems, list):
        return
    for p in problems:
        if isinstance(p, dict):
            yield p
        elif p not in (None, ""):
            yield {"message": str(p)}
