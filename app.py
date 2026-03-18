#!/usr/bin/env python3
import json
import os
import re
import shutil
import socket
import subprocess
import time
from html import unescape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote

HOST = "0.0.0.0"
PORT = 3000
APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_prev_total = None
_prev_idle = None
_btc_cache = {"ts": 0, "data": None, "last_ok_ts": 0, "fail_count": 0}
BTC_CACHE_SECONDS_OK = 900
BTC_CACHE_SECONDS_ERROR = 1800
BTC_DAYS = 5
DISPLAY_STATE_PATH = os.environ.get(
    "PIDASHBOARD_STATE_FILE",
    os.path.join(APP_BASE_DIR, "display_state.json"),
)
DISPLAY_STATE_POLL_SECONDS = 2
PAGE_ROTATE_SECONDS = 12

DO_API_BASE = "https://api.digitalocean.com/v2"
DO_METRICS_CACHE_SECONDS_OK = 300
DO_METRICS_CACHE_SECONDS_ERROR = 900
DO_METRICS_HOURS = 48
APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DO_CONFIG_PATH = os.path.join(APP_BASE_DIR, "config/digitalocean_config.json")
DO_DROPLETS_JSON = os.environ.get("DIGITALOCEAN_DROPLETS_JSON", "")
DO_DROPLET_IDS = os.environ.get("DIGITALOCEAN_DROPLET_IDS", "")
DO_TOKEN_ENV_NAMES = ("DIGITALOCEAN_TOKEN", "DO_TOKEN")
DO_API_TIMEOUT = 12

_trends_cache = {"ts": 0, "data": None, "last_ok_ts": 0, "fail_count": 0}
_do_metrics_cache = {"ts": 0, "data": None, "last_ok_ts": 0, "fail_count": 0}
TRENDS_CACHE_SECONDS_OK = 900
TRENDS_CACHE_SECONDS_ERROR = 1800
ECUADOR_TRENDS_URL = "https://trends24.in/ecuador/"
X_SEARCH_BASE_URL = "https://x.com/search?q="

SKYLINE_WEBCAM_URL = (
    "https://www.skylinewebcams.com/es/webcam/ecuador/santa-elena/"
    "santa-elena/playa-de-ballenita-capaes.html"
)
ECUADOR_CENTER = {"lat": -1.8312, "lng": -78.1834, "zoom": 6}

DEFAULT_DISPLAY_STATE = {
    "panel_right": {
        "type": "icon",
        "value": "rocket",
        "title": "Mood",
        "subtitle": "Controlled by display_state.json",
    },
    "updated_at": None,
    "source": "default",
}

ALLOWED_ICON_KEYS = {
    "rocket",
    "happy",
    "sad",
    "warning",
    "ok",
    "sleep",
    "bitcoin",
    "heart",
}


def read_file(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default



def get_hostname():
    return socket.gethostname()



def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "N/A"
    finally:
        s.close()
    return ip



def get_uptime():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            seconds = int(float(f.read().split()[0]))
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
    except Exception:
        return "N/A"



def get_load():
    try:
        load1, load5, load15 = os.getloadavg()
        return {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)}
    except Exception:
        return {"1m": "N/A", "5m": "N/A", "15m": "N/A"}



def get_cpu_usage():
    global _prev_total, _prev_idle
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            parts = f.readline().split()
        values = list(map(int, parts[1:9]))
        user, nice, system, idle, iowait, irq, softirq, steal = values
        idle_all = idle + iowait
        total = user + nice + system + idle + iowait + irq + softirq + steal

        if _prev_total is None or _prev_idle is None:
            _prev_total = total
            _prev_idle = idle_all
            return 0.0

        total_delta = total - _prev_total
        idle_delta = idle_all - _prev_idle
        _prev_total = total
        _prev_idle = idle_all

        if total_delta <= 0:
            return 0.0

        usage = 100.0 * (1.0 - idle_delta / total_delta)
        return round(max(0.0, min(100.0, usage)), 1)
    except Exception:
        return 0.0



def get_memory():
    try:
        meminfo = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                meminfo[key.strip()] = value.strip()

        total_kb = int(meminfo["MemTotal"].split()[0])
        avail_kb = int(meminfo["MemAvailable"].split()[0])
        used_kb = total_kb - avail_kb
        percent = round((used_kb / total_kb) * 100, 1)
        return {
            "total_mb": round(total_kb / 1024, 1),
            "used_mb": round(used_kb / 1024, 1),
            "available_mb": round(avail_kb / 1024, 1),
            "percent": percent,
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}



def get_disk():
    try:
        usage = shutil.disk_usage("/")
        percent = round((usage.used / usage.total) * 100, 1)
        return {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_gb": round(usage.used / (1024 ** 3), 1),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "percent": percent,
        }
    except Exception:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}



def get_cpu_temp():
    try:
        temp_milli = int(read_file("/sys/class/thermal/thermal_zone0/temp", "0"))
        return round(temp_milli / 1000.0, 1)
    except Exception:
        return None



def get_throttled():
    try:
        result = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2)
        out = result.stdout.strip()
        if "=" in out:
            return out.split("=", 1)[1].strip()
        return "N/A"
    except Exception:
        return "N/A"



def get_metrics():
    cpu_temp = get_cpu_temp()
    cpu_temp_pct = 0 if cpu_temp is None else round(max(0.0, min(100.0, (cpu_temp / 85.0) * 100.0)), 1)
    return {
        "hostname": get_hostname(),
        "ip": get_ip_address(),
        "uptime": get_uptime(),
        "load": get_load(),
        "cpu_usage": get_cpu_usage(),
        "cpu_temp": cpu_temp,
        "cpu_temp_pct": cpu_temp_pct,
        "memory": get_memory(),
        "disk": get_disk(),
        "throttled": get_throttled(),
        "timestamp": int(time.time()),
    }



def _build_btc_payload(points, updated_at, stale=False, error=None, source="Unknown"):
    min_price = None
    max_price = None
    current_price = None
    previous_price = None
    change_pct = None

    if points:
        prices = [float(p["p"]) for p in points]
        min_price = round(min(prices), 2)
        max_price = round(max(prices), 2)
        current_price = round(points[-1]["p"], 2)
        previous_price = round(points[0]["p"], 2)
        if previous_price:
            change_pct = round(((current_price - previous_price) / previous_price) * 100.0, 2)

    return {
        "ok": len(points) > 1,
        "asset": "BTC",
        "currency": "USD",
        "days": BTC_DAYS,
        "current_price": current_price,
        "change_pct": change_pct,
        "min_price": min_price,
        "max_price": max_price,
        "points": points,
        "updated_at": int(updated_at),
        "stale": stale,
        "error": error,
        "source": source,
    }



def _fetch_json(url, timeout=10):
    req = Request(
        url,
        headers={
            "User-Agent": "PiDashboard/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url, timeout=10):
    req = Request(
        url,
        headers={
            "User-Agent": "PiDashboard/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _strip_html(value):
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _topic_is_relevant(topic):
    if not topic:
        return False
    lowered = topic.lower().strip()
    if len(lowered) < 3:
        return False
    blocked_exact = {
        "oscars", "oscar", "sinners", "michael b. jordan", "michael b jordan",
        "bts is coming", "heeseung", "#let_heeeseung_do_both", "#respect_enhypen",
        "neymar", "uruguay", "colombia"
    }
    if lowered in blocked_exact:
        return False
    blocked_parts = [
        "heeseung", "enhypen", "bts", "oscars", "oscar", "michael b", "sinners",
        "kpop", "netflix", "hollywood"
    ]
    return not any(part in lowered for part in blocked_parts)


def _extract_trends24_topics(html_text, limit=2):
    section_match = re.search(
        r"Popular Active Trends</h3>(.*?)</ol>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not section_match:
        section_match = re.search(
            r"New Trends</h3>(.*?)</ol>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    topics = []
    if section_match:
        for raw in re.findall(r"<li[^>]*>(.*?)</li>", section_match.group(1), flags=re.IGNORECASE | re.DOTALL):
            topic = _strip_html(raw)
            topic = re.sub(r"\s+at\s+#?\d+$", "", topic, flags=re.IGNORECASE).strip()
            if topic and topic not in topics and _topic_is_relevant(topic):
                topics.append(topic)
            if len(topics) >= limit:
                return topics

    for raw in re.findall(r"<li[^>]*>(.*?)</li>", html_text, flags=re.IGNORECASE | re.DOTALL):
        topic = _strip_html(raw)
        topic = re.sub(r"\s+for\s+24\s+hrs$", "", topic, flags=re.IGNORECASE).strip()
        topic = re.sub(r"\s+at\s+#?\d+$", "", topic, flags=re.IGNORECASE).strip()
        if topic and topic not in topics and _topic_is_relevant(topic):
            topics.append(topic)
        if len(topics) >= limit:
            break
    return topics[:limit]


def _build_trend_posts(topics, updated_at, stale=False, error=None, source="trends24.in"):
    posts = []
    for idx, topic in enumerate(topics[:2], start=1):
        q = topic if topic.startswith("#") else f'"{topic}"'
        encoded_q = q.replace("#", "%23").replace(" ", "%20").replace('"', '%22') + "%20lang%3Aes"
        posts.append({
            "id": f"trend-{idx}",
            "topic": topic,
            "handle": "@ecuador_trends",
            "display_name": "Ecuador Trends",
            "text": f"Tema en tendencia en Ecuador: {topic}",
            "search_url": f"{X_SEARCH_BASE_URL}{encoded_q}&src=typed_query&f=live",
        })

    return {
        "ok": len(posts) > 0,
        "posts": posts,
        "updated_at": int(updated_at),
        "stale": stale,
        "error": error,
        "source": source,
    }


def get_ecuador_trending_posts():
    now = time.time()
    cached = _trends_cache.get("data")
    age = now - _trends_cache.get("ts", 0)
    min_cache_age = TRENDS_CACHE_SECONDS_ERROR if _trends_cache.get("fail_count", 0) > 0 else TRENDS_CACHE_SECONDS_OK

    if cached is not None and age < min_cache_age:
        return cached

    try:
        html_text = _fetch_text(ECUADOR_TRENDS_URL, timeout=10)
        topics = _extract_trends24_topics(html_text, limit=2)
        if not topics:
            raise ValueError("No relevant Ecuador trends found")
        data = _build_trend_posts(topics, updated_at=now, stale=False, error=None, source="trends24.in")
        _trends_cache["ts"] = now
        _trends_cache["last_ok_ts"] = now
        _trends_cache["data"] = data
        _trends_cache["fail_count"] = 0
        return data
    except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
        _trends_cache["ts"] = now
        _trends_cache["fail_count"] = _trends_cache.get("fail_count", 0) + 1
        if cached is not None:
            stale_copy = dict(cached)
            stale_copy["stale"] = True
            stale_copy["error"] = f"Trend refresh failed: {type(exc).__name__}"
            _trends_cache["data"] = stale_copy
            return stale_copy
        return _build_trend_posts([], updated_at=now, stale=True, error=f"Trend fetch failed: {type(exc).__name__}", source="trends24.in")



def _fetch_btc_history_from_kraken(days=BTC_DAYS):
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=60"
    payload = _fetch_json(url, timeout=10)

    errors = payload.get("error", [])
    if errors:
        raise ValueError("Kraken API error: " + ", ".join(map(str, errors)))

    result = payload.get("result", {})
    series = None
    for key, value in result.items():
        if key != "last" and isinstance(value, list):
            series = value
            break
    if not series:
        raise ValueError("Kraken OHLC payload missing series")

    cutoff_s = int(time.time()) - int(days) * 86400
    points = []
    for candle in series:
        if isinstance(candle, list) and len(candle) >= 5:
            ts_s = int(float(candle[0]))
            close_price = float(candle[4])
            if ts_s >= cutoff_s:
                points.append({"t": ts_s * 1000, "p": round(close_price, 2)})

    if len(points) < 2:
        raise ValueError("Kraken returned insufficient OHLC data")
    return points



def _fetch_btc_history_from_coingecko(days=BTC_DAYS):
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        f"?vs_currency=usd&days={int(days)}&interval=hourly"
    )
    payload = _fetch_json(url, timeout=10)

    raw_prices = payload.get("prices", [])
    points = []
    for item in raw_prices:
        if isinstance(item, list) and len(item) >= 2:
            points.append({"t": int(item[0]), "p": round(float(item[1]), 2)})
    if len(points) < 2:
        raise ValueError("CoinGecko returned insufficient market data")
    return points



def get_btc_history(days=BTC_DAYS):
    now = time.time()
    cached = _btc_cache.get("data")
    age = now - _btc_cache.get("ts", 0)
    min_cache_age = BTC_CACHE_SECONDS_ERROR if _btc_cache.get("fail_count", 0) > 0 else BTC_CACHE_SECONDS_OK

    if cached is not None and age < min_cache_age:
        return cached

    providers = [
        ("Kraken", _fetch_btc_history_from_kraken),
        ("CoinGecko", _fetch_btc_history_from_coingecko),
    ]

    last_error = None
    for provider_name, fetcher in providers:
        try:
            points = fetcher(days=days)
            data = _build_btc_payload(points, updated_at=now, stale=False, error=None, source=provider_name)
            _btc_cache["ts"] = now
            _btc_cache["last_ok_ts"] = now
            _btc_cache["data"] = data
            _btc_cache["fail_count"] = 0
            return data
        except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            last_error = f"{provider_name}: {type(exc).__name__}"

    _btc_cache["ts"] = now
    _btc_cache["fail_count"] = _btc_cache.get("fail_count", 0) + 1
    if cached is not None:
        stale_copy = dict(cached)
        stale_copy["stale"] = True
        stale_copy["error"] = f"BTC refresh failed: {last_error or 'unknown error'}"
        _btc_cache["data"] = stale_copy
        return stale_copy
    return _build_btc_payload([], updated_at=now, stale=True, error=f"BTC fetch failed: {last_error or 'unknown error'}", source="Kraken")



def _copy_default_state():
    state = json.loads(json.dumps(DEFAULT_DISPLAY_STATE))
    state["path"] = DISPLAY_STATE_PATH
    state["exists"] = os.path.exists(DISPLAY_STATE_PATH)
    state["valid"] = True
    return state



def get_display_state():
    state = _copy_default_state()

    try:
        with open(DISPLAY_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        state["error"] = "display_state.json not found; using default state"
        return state
    except (json.JSONDecodeError, OSError) as exc:
        state["error"] = f"Invalid display_state.json: {type(exc).__name__}"
        state["valid"] = False
        return state

    if not isinstance(data, dict):
        state["error"] = "display_state.json root must be an object"
        state["valid"] = False
        return state

    panel = data.get("panel_right")
    if not isinstance(panel, dict):
        state["error"] = "display_state.json must contain panel_right object"
        state["valid"] = False
        return state

    panel_type = str(panel.get("type", "icon")).strip().lower()
    value = panel.get("value", "rocket")
    title = str(panel.get("title", "Mood")).strip() or "Mood"
    subtitle = str(panel.get("subtitle", "")).strip()

    normalized = {
        "type": panel_type,
        "value": value,
        "title": title,
        "subtitle": subtitle,
    }

    if panel_type == "icon":
        icon_key = str(value).strip().lower()
        if icon_key not in ALLOWED_ICON_KEYS:
            normalized["value"] = "warning"
            state["error"] = f"Unknown icon '{icon_key}', using warning"
            state["valid"] = False
    elif panel_type == "emoji":
        normalized["value"] = str(value)
    elif panel_type == "text":
        normalized["value"] = str(value)
    else:
        normalized["type"] = "icon"
        normalized["value"] = "warning"
        state["error"] = f"Unsupported panel_right.type '{panel_type}'"
        state["valid"] = False

    state.update({
        "panel_right": normalized,
        "updated_at": data.get("updated_at"),
        "source": data.get("source", "external"),
        "exists": True,
    })
    return state



def _load_do_config():
    try:
        with open(DO_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_do_token():
    config = _load_do_config()
    token = str(config.get("token") or config.get("api_token") or "").strip()
    if token:
        return token
    for key in DO_TOKEN_ENV_NAMES:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _parse_do_droplets_config():
    droplets = []
    config = _load_do_config()

    raw_servers = config.get("servers")
    if isinstance(raw_servers, list):
        for item in raw_servers[:3]:
            if isinstance(item, dict) and item.get("id") is not None:
                droplets.append({
                    "id": str(item.get("id")).strip(),
                    "name": str(item.get("name") or item.get("hostname") or item.get("id")).strip(),
                })

    if not droplets and DO_DROPLETS_JSON.strip():
        try:
            raw = json.loads(DO_DROPLETS_JSON)
            if isinstance(raw, list):
                for item in raw[:3]:
                    if isinstance(item, dict) and item.get("id") is not None:
                        droplets.append({
                            "id": str(item.get("id")).strip(),
                            "name": str(item.get("name") or item.get("hostname") or item.get("id")).strip(),
                        })
        except Exception:
            pass

    if not droplets:
        raw_ids = str(config.get("droplet_ids") or "").strip()
        if raw_ids:
            for raw_id in raw_ids.split(","):
                raw_id = raw_id.strip()
                if raw_id:
                    droplets.append({"id": raw_id, "name": f"Droplet {raw_id}"})

    if not droplets and DO_DROPLET_IDS.strip():
        for raw_id in DO_DROPLET_IDS.split(","):
            raw_id = raw_id.strip()
            if raw_id:
                droplets.append({"id": raw_id, "name": f"Droplet {raw_id}"})

    unique = []
    seen = set()
    for item in droplets:
        item_id = item["id"]
        if item_id and item_id not in seen:
            seen.add(item_id)
            unique.append(item)
    return unique[:3]


def _fetch_do_json(path, token, timeout=DO_API_TIMEOUT):
    url = f"{DO_API_BASE}{path}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PiDashboard/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
            result_count = len((((data or {}).get("data") or {}).get("result") or []))
            if result_count == 0:
                print(f"[DO] GET {path[:80]} → {response.status} (0 series) RAW={raw[:300]}", flush=True)
            else:
                print(f"[DO] GET {path[:80]} → {response.status} ({result_count} series)", flush=True)
            return data
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f"[DO] ERROR {exc.code} {path[:80]} | {body}", flush=True)
        raise
    except Exception as exc:
        print(f"[DO] ERROR {type(exc).__name__} {path[:80]} | {exc}", flush=True)
        raise


def _get_do_metric_series(path, token):
    payload = _fetch_do_json(path, token, timeout=DO_API_TIMEOUT)
    result = (((payload or {}).get("data") or {}).get("result") or [])
    if not result:
        return []
    series = []
    for item in result:
        for point in item.get("values", []) or []:
            try:
                ts = int(float(point[0]))
                value = float(point[1])
                series.append((ts, value))
            except Exception:
                continue
    series.sort(key=lambda x: x[0])
    return series


def _downsample_metric_series(points, target=24):
    if len(points) <= target:
        return [{"t": ts * 1000, "v": round(value, 3)} for ts, value in points]
    step = max(1, len(points) // target)
    sampled = points[::step]
    if sampled[-1][0] != points[-1][0]:
        sampled.append(points[-1])
    return [{"t": ts * 1000, "v": round(value, 3)} for ts, value in sampled[:target-1] + [sampled[-1]] if sampled]


def _combine_series(a_points, b_points, fn):
    if not a_points or not b_points:
        return []
    b_map = {ts: value for ts, value in b_points}
    merged = []
    for ts, a_value in a_points:
        if ts in b_map:
            try:
                merged.append((ts, fn(a_value, b_map[ts])))
            except Exception:
                continue
    return merged


def _latest_value(points, default=0.0):
    if not points:
        return default
    return points[-1][1]


def _clamp(value, low=0.0, high=100.0):
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return low


def _format_do_server_payload(server, cpu_points, ram_points, disk_points, bw_points, meta=None):
    cpu_latest = round(_clamp(_latest_value(cpu_points, 0.0)), 1)
    ram_latest = round(_clamp(_latest_value(ram_points, 0.0)), 1)
    disk_latest = round(_clamp(_latest_value(disk_points, 0.0)), 1)
    bw_latest = round(max(0.0, _latest_value(bw_points, 0.0)), 2)

    return {
        "id": server["id"],
        "name": server["name"],
        "cpu_pct": cpu_latest,
        "ram_pct": ram_latest,
        "disk_pct": disk_latest,
        "bandwidth_mbps": bw_latest,
        "series": {
            "cpu": _downsample_metric_series(cpu_points),
            "ram": _downsample_metric_series(ram_points),
            "disk": _downsample_metric_series(disk_points),
            "bandwidth": _downsample_metric_series(bw_points),
        },
        "meta": meta or {},
    }


def get_digitalocean_metrics():
    now = int(time.time())
    cached = _do_metrics_cache.get("data")
    age = now - int(_do_metrics_cache.get("ts", 0) or 0)
    min_cache_age = DO_METRICS_CACHE_SECONDS_ERROR if _do_metrics_cache.get("fail_count", 0) > 0 else DO_METRICS_CACHE_SECONDS_OK
    if cached is not None and age < min_cache_age:
        return cached

    token = _read_do_token()
    droplets = _parse_do_droplets_config()

    if not token:
        data = {
            "ok": False,
            "error": f"Missing DigitalOcean token. Configure {DO_CONFIG_PATH}.",
            "updated_at": now,
            "hours": DO_METRICS_HOURS,
            "servers": [],
            "stale": cached is not None,
            "source": "DigitalOcean Monitoring API",
        }
        if cached is not None:
            stale_copy = dict(cached)
            stale_copy["stale"] = True
            stale_copy["error"] = data["error"]
            return stale_copy
        return data

    if not droplets:
        data = {
            "ok": False,
            "error": f"Missing droplet config. Configure servers in {DO_CONFIG_PATH}.",
            "updated_at": now,
            "hours": DO_METRICS_HOURS,
            "servers": [],
            "stale": cached is not None,
            "source": "DigitalOcean Monitoring API",
        }
        if cached is not None:
            stale_copy = dict(cached)
            stale_copy["stale"] = True
            stale_copy["error"] = data["error"]
            return stale_copy
        return data

    start = now - DO_METRICS_HOURS * 3600
    end = now
    servers = []

    print(f"[DO] Fetching metrics for {len(droplets[:3])} droplet(s): {[d['name'] for d in droplets[:3]]}", flush=True)
    try:
        for server in droplets[:3]:
            host_id = quote(str(server["id"]), safe="")
            common = f"host_id={host_id}&start={start}&end={end}"
            print(f"[DO] Fetching droplet '{server['name']}' (id={server['id']})", flush=True)

            cpu_points = _get_do_metric_series(f"/monitoring/metrics/droplet/cpu?{common}", token)

            mem_avail = _get_do_metric_series(f"/monitoring/metrics/droplet/memory_available?{common}", token)
            mem_total = _get_do_metric_series(f"/monitoring/metrics/droplet/memory_total?{common}", token)
            ram_points = _combine_series(mem_avail, mem_total, lambda avail, total: 0.0 if total <= 0 else (1.0 - (avail / total)) * 100.0)

            fs_free = _get_do_metric_series(f"/monitoring/metrics/droplet/filesystem_free?{common}", token)
            fs_size = _get_do_metric_series(f"/monitoring/metrics/droplet/filesystem_size?{common}", token)
            disk_points = _combine_series(fs_free, fs_size, lambda free, size: 0.0 if size <= 0 else (1.0 - (free / size)) * 100.0)

            bw_in = _get_do_metric_series(f"/monitoring/metrics/droplet/bandwidth?host_id={host_id}&interface=public&direction=inbound&start={start}&end={end}", token)
            bw_out = _get_do_metric_series(f"/monitoring/metrics/droplet/bandwidth?host_id={host_id}&interface=public&direction=outbound&start={start}&end={end}", token)
            bw_points = _combine_series(bw_in, bw_out, lambda inbound, outbound: max(0.0, inbound) + max(0.0, outbound))

            payload = _format_do_server_payload(server, cpu_points, ram_points, disk_points, bw_points, meta={"bandwidth_interface": "public", "bandwidth_mode": "in+out"})
            print(
                f"[DO]   '{server['name']}': cpu={payload['cpu_pct']}% ({len(cpu_points)}pts)"
                f" ram={payload['ram_pct']}% ({len(ram_points)}pts)"
                f" disk={payload['disk_pct']}% ({len(disk_points)}pts)"
                f" bw={payload['bandwidth_mbps']}Mbps ({len(bw_points)}pts)",
                flush=True,
            )
            servers.append(payload)

        data = {
            "ok": len(servers) > 0,
            "error": None if servers else "No server metrics available.",
            "updated_at": now,
            "hours": DO_METRICS_HOURS,
            "servers": servers,
            "stale": False,
            "source": "DigitalOcean Monitoring API",
        }
        _do_metrics_cache["ts"] = now
        _do_metrics_cache["last_ok_ts"] = now
        _do_metrics_cache["data"] = data
        _do_metrics_cache["fail_count"] = 0
        return data

    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[DO] FETCH FAILED: {type(exc).__name__}: {exc}", flush=True)
        _do_metrics_cache["ts"] = now
        _do_metrics_cache["fail_count"] = _do_metrics_cache.get("fail_count", 0) + 1
        if cached is not None:
            stale_copy = dict(cached)
            stale_copy["stale"] = True
            stale_copy["error"] = f"DigitalOcean refresh failed: {type(exc).__name__}"
            _do_metrics_cache["data"] = stale_copy
            return stale_copy
        return {
            "ok": False,
            "error": f"DigitalOcean fetch failed: {type(exc).__name__}",
            "updated_at": now,
            "hours": DO_METRICS_HOURS,
            "servers": [],
            "stale": True,
            "source": "DigitalOcean Monitoring API",
        }

HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=1280, initial-scale=1, maximum-scale=1, user-scalable=no">
  <title>Pi Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  <style>
    :root {
      --bg: #0b1020;
      --panel: rgba(255,255,255,0.08);
      --panel-strong: rgba(255,255,255,0.12);
      --text: #eef2ff;
      --muted: #a8b3cf;
      --accent: #67e8f9;
      --accent2: #8b5cf6;
      --border: rgba(255,255,255,0.10);
      --shadow: 0 14px 36px rgba(0,0,0,0.24);
      --ok: #22c55e;
      --warn: #f59e0b;
      --danger: #ef4444;
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      width: 1280px;
      height: 400px;
      overflow: hidden;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(103,232,249,0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(139,92,246,0.16), transparent 32%),
        linear-gradient(180deg, #0b1020 0%, #11162b 100%);
      color: var(--text);
    }

    body { padding: 14px; }

    .viewport {
      width: 100%;
      height: 100%;
      overflow: hidden;
      position: relative;
    }

    .pages {
      width: 300%;
      height: 100%;
      display: flex;
      transition: transform 0.7s ease;
      will-change: transform;
    }

    .page {
      width: 33.333333%;
      height: 100%;
      flex: 0 0 33.333333%;
      min-width: 0;
    }

    .layout {
      height: 100%;
      display: grid;
      grid-template-columns: 440px minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }

    .left {
      display: grid;
      grid-template-rows: 108px 1fr;
      gap: 14px;
      min-height: 0;
    }

    .hero, .card {
      border-radius: 24px;
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }

    .hero {
      padding: 14px 18px;
      background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.05));
    }

    .title {
      font-size: 16px;
      color: var(--muted);
      margin-bottom: 8px;
      letter-spacing: 0.03em;
    }

    .host {
      font-size: 26px;
      font-weight: 800;
      line-height: 1.05;
      margin: 0 0 6px 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sub {
      font-size: 15px;
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: repeat(2, minmax(0, 1fr));
      gap: 14px;
      min-height: 0;
    }

    .card {
      background: var(--panel);
      padding: 12px 14px;
      overflow: hidden;
    }

    .label {
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    .metric-main {
      font-size: 24px;
      font-weight: 800;
      line-height: 1.02;
      margin-bottom: 6px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .metric-sub {
      font-size: 13px;
      color: var(--muted);
      line-height: 1.2;
      min-height: 22px;
    }

    .bar-wrap {
      height: 14px;
      background: rgba(255,255,255,0.12);
      border-radius: 999px;
      overflow: hidden;
      margin-top: 8px;
    }

    .bar {
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      transition: width 0.45s ease;
      box-shadow: 0 0 14px rgba(103,232,249,0.25);
    }

    .middle, .right { min-height: 0; }

    .chart-card, .map-card, .camera-card, .tweets-card {
      height: 100%;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 10px;
      background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05));
      padding: 12px 14px;
    }

    .chart-top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }

    .btc-title, .map-title, .camera-title, .tweets-title {
      font-size: 18px;
      color: var(--muted);
      margin-bottom: 4px;
    }

    .btc-price {
      font-size: 40px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 6px;
    }

    .btc-change {
      font-size: 15px;
      font-weight: 700;
      min-height: 18px;
    }

    .btc-meta {
      text-align: right;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      padding-top: 3px;
      min-width: 105px;
    }

    .chart-wrap, .map-wrap, .camera-wrap, .tweets-wrap {
      position: relative;
      min-height: 0;
      border-radius: 20px;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      border: 1px solid rgba(255,255,255,0.06);
    }

    canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .chart-footer, .map-footer, .camera-footer, .tweets-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
      gap: 8px;
    }

    .pill {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--panel-strong);
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .emoji-card {
      height: 100%;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05));
      position: relative;
      padding: 0;
    }

    .panel-right-title {
      position: absolute;
      left: 16px;
      top: 14px;
      font-size: 16px;
      color: var(--muted);
      letter-spacing: 0.03em;
      z-index: 2;
      max-width: calc(100% - 32px);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .panel-right-subtitle {
      position: absolute;
      left: 16px;
      bottom: 12px;
      font-size: 12px;
      color: var(--muted);
      z-index: 2;
      max-width: calc(100% - 32px);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .panel-right-stage {
      width: 100%;
      height: 100%;
      display: grid;
      place-items: center;
      padding: 40px 28px 34px 28px;
    }

    .emoji-svg {
      width: 76%;
      height: 76%;
      filter: drop-shadow(0 8px 24px rgba(0,0,0,0.28));
      user-select: none;
    }

    .emoji-text {
      font-size: 150px;
      line-height: 1;
      filter: drop-shadow(0 8px 24px rgba(0,0,0,0.28));
      user-select: none;
    }

    .panel-text {
      font-size: 42px;
      line-height: 1.1;
      font-weight: 800;
      text-align: center;
      max-width: 90%;
      word-break: break-word;
      color: var(--text);
      text-shadow: 0 8px 24px rgba(0,0,0,0.28);
    }

    .camera-iframe {
      width: 100%;
      height: 100%;
      border: 0;
      background: #0b1020;
    }


    .tweets-list {
      display: grid;
      grid-template-rows: 1fr 1fr;
      gap: 10px;
      height: 100%;
      min-height: 0;
      padding: 2px;
    }

    .tweet-card {
      border-radius: 18px;
      padding: 12px 14px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.08);
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 8px;
      overflow: hidden;
    }

    .tweet-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }

    .tweet-user {
      min-width: 0;
    }

    .tweet-name {
      font-size: 14px;
      font-weight: 800;
      color: var(--text);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .tweet-handle {
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .tweet-topic {
      font-size: 11px;
      font-weight: 800;
      color: var(--accent);
      background: rgba(103,232,249,0.12);
      border: 1px solid rgba(103,232,249,0.18);
      border-radius: 999px;
      padding: 5px 8px;
      white-space: nowrap;
      max-width: 45%;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .tweet-text {
      font-size: 20px;
      line-height: 1.2;
      color: var(--text);
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
    }

    .tweet-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .tweet-link {
      color: var(--text);
      text-decoration: none;
      font-weight: 700;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.08);
    }

    .tweet-link:hover {
      background: rgba(255,255,255,0.12);
    }

    .camera-overlay {
      position: absolute;
      inset: auto 12px 12px 12px;
      padding: 8px 10px;
      border-radius: 14px;
      background: rgba(11, 16, 32, 0.66);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      backdrop-filter: blur(8px);
      border: 1px solid rgba(255,255,255,0.08);
      pointer-events: none;
    }

    .map-root {
      width: 100%;
      height: 100%;
      border-radius: 20px;
    }

    .page-indicator {
      position: absolute;
      right: 10px;
      top: 8px;
      display: flex;
      gap: 6px;
      z-index: 4;
    }

    .page-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.20);
      transition: transform 0.35s ease, background 0.35s ease;
    }

    .page-dot.active {
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      transform: scale(1.25);
      box-shadow: 0 0 10px rgba(103,232,249,0.35);
    }

    .leaflet-container {
      background: #0f172a;
      font: inherit;
    }

    .leaflet-control-attribution {
      background: rgba(11,16,32,0.72);
      color: var(--muted);
      border-radius: 12px;
      margin: 0 8px 8px 0;
      padding: 4px 8px;
      backdrop-filter: blur(8px);
    }

    .leaflet-control-attribution a {
      color: var(--text);
    }


    .servers-card {
      height: 100%;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 10px;
      background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05));
      padding: 12px 14px;
    }

    .servers-wrap {
      display: grid;
      grid-template-rows: repeat(3, 1fr);
      gap: 10px;
      min-height: 0;
    }

    .server-row {
      border-radius: 18px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.08);
      display: grid;
      grid-template-columns: 190px repeat(4, 1fr);
      gap: 10px;
      min-height: 0;
      align-items: stretch;
    }

    .server-meta {
      min-width: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 6px;
    }

    .server-name {
      font-size: 18px;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .server-id {
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .server-chip-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .server-chip {
      font-size: 11px;
      padding: 4px 7px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      color: var(--text);
      border: 1px solid rgba(255,255,255,0.06);
      white-space: nowrap;
    }

    .mini-metric {
      min-width: 0;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 4px;
      align-content: start;
    }

    .mini-label {
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    .mini-value {
      font-size: 18px;
      font-weight: 800;
      line-height: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sparkline {
      width: 100%;
      height: 46px;
      display: block;
      border-radius: 12px;
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      border: 1px solid rgba(255,255,255,0.05);
    }

    .server-empty {
      height: 100%;
      display: grid;
      place-items: center;
      text-align: center;
      color: var(--muted);
      border-radius: 18px;
      border: 1px dashed rgba(255,255,255,0.12);
      padding: 20px;
    }

    .up { color: var(--ok); }
    .down { color: var(--danger); }
    .warning { color: var(--warn); }
    .muted { color: var(--muted); }
  </style>
</head>
<body>
  <div class="viewport">
    <div class="page-indicator">
      <div class="page-dot active" id="page_dot_0"></div>
      <div class="page-dot" id="page_dot_1"></div>
      <div class="page-dot" id="page_dot_2"></div>
    </div>

    <div class="pages" id="pages">
      <section class="page">
        <div class="layout">
          <div class="left">
            <div class="hero">
              <div class="title">Raspberry Pi Dashboard</div>
              <div class="host" id="hostname">raspberrypi</div>
              <div class="sub"><span id="ip">0.0.0.0</span> · uptime <span id="uptime">0h 0m</span></div>
            </div>

            <div class="metrics-grid">
              <div class="card">
                <div class="label">CPU Usage</div>
                <div class="metric-main" id="cpu_usage">0.0%</div>
                <div class="metric-sub">Load: <span id="load1">0.00</span> / <span id="load5">0.00</span> / <span id="load15">0.00</span></div>
                <div class="bar-wrap"><div class="bar" id="cpu_bar"></div></div>
              </div>

              <div class="card">
                <div class="label">CPU Temp</div>
                <div class="metric-main" id="cpu_temp">0.0°C</div>
                <div class="metric-sub">Throttled: <span id="throttled">N/A</span></div>
                <div class="bar-wrap"><div class="bar" id="temp_bar"></div></div>
              </div>

              <div class="card">
                <div class="label">Memory</div>
                <div class="metric-main"><span id="mem_used">0</span> / <span id="mem_total">0</span> MB</div>
                <div class="metric-sub">Used <span id="mem_pct">0%</span></div>
                <div class="bar-wrap"><div class="bar" id="mem_bar"></div></div>
              </div>

              <div class="card">
                <div class="label">Disk</div>
                <div class="metric-main"><span id="disk_used">0</span> / <span id="disk_total">0</span> GB</div>
                <div class="metric-sub">Used <span id="disk_pct">0%</span> · Updated <span id="updated">--:--:--</span></div>
                <div class="bar-wrap"><div class="bar" id="disk_bar"></div></div>
              </div>
            </div>
          </div>

          <div class="middle">
            <div class="card chart-card">
              <div class="chart-top">
                <div>
                  <div class="btc-title">Bitcoin · last 5 days</div>
                  <div class="btc-price" id="btc_price">$--</div>
                  <div class="btc-change muted" id="btc_change">Loading BTC data...</div>
                </div>
                <div class="btc-meta">
                  <div>Min: <span id="btc_min">--</span></div>
                  <div>Max: <span id="btc_max">--</span></div>
                  <div>Source: <span id="btc_source">Kraken</span></div>
                </div>
              </div>

              <div class="chart-wrap">
                <canvas id="btc_chart"></canvas>
              </div>

              <div class="chart-footer">
                <div class="pill">BTC / USD</div>
                <div id="btc_updated">BTC cache 15 min</div>
              </div>
            </div>
          </div>

          <div class="right">
            <div class="card emoji-card">
              <div class="panel-right-title" id="panel_right_title">Mood</div>
              <div class="panel-right-stage" id="panel_right_stage"></div>
              <div class="panel-right-subtitle" id="panel_right_subtitle">Controlled by display_state.json</div>
            </div>
          </div>
        </div>
      </section>

      <section class="page">
        <div class="layout">
          <div class="left">
            <div class="card tweets-card">
              <div>
                <div class="tweets-title">Ecuador · tendencias en X</div>
                <div class="metric-sub">Dos temas relevantes con acceso directo a búsqueda en vivo</div>
              </div>

              <div class="tweets-wrap">
                <div class="tweets-list" id="trends_list">
                  <div class="tweet-card">
                    <div class="tweet-head">
                      <div class="tweet-user">
                        <div class="tweet-name">Cargando tendencias…</div>
                        <div class="tweet-handle">@ecuador_trends</div>
                      </div>
                    </div>
                    <div class="tweet-text">Esperando datos…</div>
                    <div class="tweet-actions">
                      <span>Actualizando…</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="tweets-footer">
                <div class="pill">X / Ecuador</div>
                <div id="trends_updated">Cache 15 min</div>
              </div>
            </div>
          </div>

          <div class="middle">
            <div class="card map-card">
              <div>
                <div class="map-title">Map · Ecuador</div>
                <div class="metric-sub">Centered on Ecuador</div>
              </div>

              <div class="map-wrap">
                <div id="map_page_2" class="map-root"></div>
              </div>

              <div class="map-footer">
                <div class="pill">Map</div>
                <div id="map_footer_text">Waiting for map…</div>
              </div>
            </div>
          </div>

          <div class="right">
            <div class="card emoji-card">
              <div class="panel-right-title" id="panel_right_title_p2">Mood</div>
              <div class="panel-right-stage" id="panel_right_stage_p2"></div>
              <div class="panel-right-subtitle" id="panel_right_subtitle_p2">Controlled by display_state.json</div>
            </div>
          </div>
        </div>
      </section>

      <section class="page">
        <div class="layout">
          <div class="left" style="grid-column: 1 / span 3; grid-template-rows: 1fr;">
            <div class="card servers-card">
              <div>
                <div class="tweets-title">DigitalOcean · 3 servidores · últimas 48 h</div>
                <div class="metric-sub">Cada fila muestra CPU, RAM, disco y ancho de banda público total para un servidor</div>
              </div>

              <div class="servers-wrap" id="do_servers_wrap">
                <div class="server-empty">Configura tus Droplets en variables de entorno para ver métricas aquí.</div>
              </div>

              <div class="tweets-footer">
                <div class="pill">DigitalOcean Monitoring API</div>
                <div id="do_updated">Esperando configuración…</div>
              </div>
            </div>
          </div>
        </div>
      </section>

    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const chartCanvas = document.getElementById("btc_chart");
    const PAGES = document.getElementById("pages");
    const PAGE_ROTATE_MS = __PAGE_ROTATE_MS__;
    const ECUADOR_CENTER = { lat: __ECUADOR_LAT__, lng: __ECUADOR_LNG__, zoom: __ECUADOR_ZOOM__ };
    let lastGoodBtcPoints = [];
    let currentPage = 0;
    let lastDoData = [];
    let mapPage2 = null;
    let mapWasResized = false;

    function setBar(id, percent) {
      const p = Math.max(0, Math.min(100, Number(percent || 0)));
      document.getElementById(id).style.width = p + "%";
    }

    function formatUsd(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "$--";
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0
      }).format(Number(value));
    }

    function formatSignedPct(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
      const num = Number(value);
      return (num >= 0 ? "+" : "") + num.toFixed(2) + "%";
    }

    function drawChart(points) {
      const ctx = chartCanvas.getContext("2d");
      const rect = chartCanvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      chartCanvas.width = Math.max(1, Math.floor(rect.width * dpr));
      chartCanvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      const pad = { top: 16, right: 18, bottom: 24, left: 18 };
      const cw = w - pad.left - pad.right;
      const ch = h - pad.top - pad.bottom;

      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.lineWidth = 1;
      for (let i = 0; i < 4; i++) {
        const y = pad.top + (ch / 3) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(w - pad.right, y);
        ctx.stroke();
      }

      if (!points || points.length < 2) {
        ctx.fillStyle = "rgba(255,255,255,0.6)";
        ctx.font = "14px Inter, sans-serif";
        ctx.fillText("No BTC data available", pad.left, pad.top + 18);
        return;
      }

      const prices = points.map(p => Number(p.p));
      const min = Math.min(...prices);
      const max = Math.max(...prices);
      const span = Math.max(1, max - min);
      const xFor = (i) => pad.left + (i / (points.length - 1)) * cw;
      const yFor = (price) => pad.top + ((max - price) / span) * ch;

      ctx.beginPath();
      for (let i = 0; i < points.length; i++) {
        const x = xFor(i);
        const y = yFor(points[i].p);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }

      const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
      gradient.addColorStop(0, "rgba(103,232,249,0.95)");
      gradient.addColorStop(1, "rgba(139,92,246,0.95)");
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.lineTo(pad.left + cw, pad.top + ch);
      ctx.lineTo(pad.left, pad.top + ch);
      ctx.closePath();

      const area = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
      area.addColorStop(0, "rgba(103,232,249,0.24)");
      area.addColorStop(1, "rgba(139,92,246,0.03)");
      ctx.fillStyle = area;
      ctx.fill();

      const last = points[points.length - 1];
      const lx = xFor(points.length - 1);
      const ly = yFor(last.p);
      ctx.beginPath();
      ctx.arc(lx, ly, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = "#eef2ff";
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.55)";
      ctx.font = "12px Inter, sans-serif";
      ctx.fillText("5d ago", pad.left, h - 6);
      const label = "now";
      const m = ctx.measureText(label);
      ctx.fillText(label, w - pad.right - m.width, h - 6);
    }

    function iconSvg(name) {
      const svgs = {
        rocket: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="rocket" role="img">
            <defs>
              <linearGradient id="rocketBody" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#eef2ff" />
                <stop offset="100%" stop-color="#c7d2fe" />
              </linearGradient>
              <linearGradient id="rocketAccent" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#67e8f9" />
                <stop offset="100%" stop-color="#8b5cf6" />
              </linearGradient>
              <linearGradient id="flame" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#fde68a" />
                <stop offset="55%" stop-color="#fb923c" />
                <stop offset="100%" stop-color="#ef4444" />
              </linearGradient>
            </defs>
            <g transform="translate(128 128) rotate(-18) translate(-128 -128)">
              <path d="M128 28 C164 44, 194 92, 188 136 C182 178, 152 208, 128 224 C104 208, 74 178, 68 136 C62 92, 92 44, 128 28 Z" fill="url(#rocketBody)" stroke="rgba(255,255,255,0.55)" stroke-width="4"/>
              <circle cx="128" cy="110" r="24" fill="#0f172a" stroke="url(#rocketAccent)" stroke-width="8"/>
              <path d="M87 144 L58 172 L84 178 L96 154 Z" fill="url(#rocketAccent)" opacity="0.95"/>
              <path d="M169 144 L198 172 L172 178 L160 154 Z" fill="url(#rocketAccent)" opacity="0.95"/>
              <path d="M112 194 C116 208, 120 219, 128 232 C136 219, 140 208, 144 194 Z" fill="url(#flame)"/>
              <path d="M120 192 C123 201, 125 208, 128 216 C131 208, 133 201, 136 192 Z" fill="#fef3c7" opacity="0.9"/>
            </g>
          </svg>`,
        happy: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="happy" role="img">
            <defs>
              <radialGradient id="faceHappy" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stop-color="#fde68a" />
                <stop offset="100%" stop-color="#f59e0b" />
              </radialGradient>
            </defs>
            <circle cx="128" cy="128" r="88" fill="url(#faceHappy)"/>
            <circle cx="96" cy="106" r="10" fill="#0f172a"/>
            <circle cx="160" cy="106" r="10" fill="#0f172a"/>
            <path d="M84 146 C98 170, 118 182, 128 182 C138 182, 158 170, 172 146" fill="none" stroke="#0f172a" stroke-width="10" stroke-linecap="round"/>
          </svg>`,
        sad: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="sad" role="img">
            <defs>
              <radialGradient id="faceSad" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stop-color="#c4b5fd" />
                <stop offset="100%" stop-color="#8b5cf6" />
              </radialGradient>
            </defs>
            <circle cx="128" cy="128" r="88" fill="url(#faceSad)"/>
            <circle cx="96" cy="106" r="10" fill="#0f172a"/>
            <circle cx="160" cy="106" r="10" fill="#0f172a"/>
            <path d="M84 174 C100 150, 116 142, 128 142 C140 142, 156 150, 172 174" fill="none" stroke="#0f172a" stroke-width="10" stroke-linecap="round"/>
            <path d="M176 124 C188 138, 188 154, 176 166 C164 154, 164 138, 176 124 Z" fill="#67e8f9" opacity="0.95"/>
          </svg>`,
        warning: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="warning" role="img">
            <defs>
              <linearGradient id="warnTri" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#fde68a" />
                <stop offset="100%" stop-color="#f59e0b" />
              </linearGradient>
            </defs>
            <path d="M128 34 L222 206 H34 Z" fill="url(#warnTri)" stroke="rgba(255,255,255,0.55)" stroke-width="5"/>
            <rect x="118" y="86" width="20" height="66" rx="10" fill="#0f172a"/>
            <circle cx="128" cy="178" r="10" fill="#0f172a"/>
          </svg>`,
        ok: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="ok" role="img">
            <defs>
              <linearGradient id="okCircle" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#67e8f9" />
                <stop offset="100%" stop-color="#22c55e" />
              </linearGradient>
            </defs>
            <circle cx="128" cy="128" r="88" fill="rgba(255,255,255,0.05)" stroke="url(#okCircle)" stroke-width="18"/>
            <path d="M86 132 L116 162 L174 98" fill="none" stroke="#eef2ff" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>`,
        sleep: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="sleep" role="img">
            <defs>
              <radialGradient id="moonGrad" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stop-color="#e9d5ff" />
                <stop offset="100%" stop-color="#8b5cf6" />
              </radialGradient>
            </defs>
            <path d="M156 42 C118 56, 90 92, 90 134 C90 176, 118 212, 156 226 C88 224, 34 169, 34 101 C34 33, 88 -22, 156 -24 C168 -24, 178 -22, 188 -18 C168 -4, 156 18, 156 42 Z" fill="url(#moonGrad)" transform="translate(18 20)"/>
            <text x="162" y="82" fill="#eef2ff" font-size="36" font-weight="800">Z</text>
            <text x="186" y="56" fill="#c7d2fe" font-size="24" font-weight="800">z</text>
          </svg>`,
        bitcoin: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="bitcoin" role="img">
            <defs>
              <radialGradient id="btcCoin" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stop-color="#fde68a" />
                <stop offset="100%" stop-color="#f97316" />
              </radialGradient>
            </defs>
            <circle cx="128" cy="128" r="88" fill="url(#btcCoin)"/>
            <text x="128" y="156" text-anchor="middle" fill="#fff7ed" font-size="112" font-weight="900">₿</text>
          </svg>`,
        heart: `
          <svg class="emoji-svg" viewBox="0 0 256 256" aria-label="heart" role="img">
            <defs>
              <linearGradient id="heartGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#fb7185" />
                <stop offset="100%" stop-color="#e11d48" />
              </linearGradient>
            </defs>
            <path d="M128 214 L112 200 C54 149 24 122 24 84 C24 52 48 28 80 28 C98 28 116 36 128 50 C140 36 158 28 176 28 C208 28 232 52 232 84 C232 122 202 149 144 200 Z" fill="url(#heartGrad)"/>
          </svg>`,
      };
      return svgs[name] || svgs.warning;
    }

    function renderPanelRightTo(state, ids) {
      const panel = state && state.panel_right ? state.panel_right : { type: "icon", value: "warning" };
      const stage = document.getElementById(ids.stage);
      document.getElementById(ids.title).textContent = panel.title || "Mood";
      document.getElementById(ids.subtitle).textContent = panel.subtitle || "";

      if (panel.type === "icon") {
        stage.innerHTML = iconSvg(String(panel.value || "warning").toLowerCase());
        return;
      }
      if (panel.type === "emoji") {
        stage.innerHTML = `<div class="emoji-text">${String(panel.value || "🙂")}</div>`;
        return;
      }
      if (panel.type === "text") {
        stage.innerHTML = `<div class="panel-text">${String(panel.value || "")}</div>`;
        return;
      }
      stage.innerHTML = iconSvg("warning");
    }

    function renderPanelRight(state) {
      renderPanelRightTo(state, {
        title: "panel_right_title",
        stage: "panel_right_stage",
        subtitle: "panel_right_subtitle"
      });
      renderPanelRightTo(state, {
        title: "panel_right_title_p2",
        stage: "panel_right_stage_p2",
        subtitle: "panel_right_subtitle_p2"
      });
    }

    function ensureMapPage2() {
      if (mapPage2) return mapPage2;

      mapPage2 = L.map("map_page_2", {
        zoomControl: false,
        attributionControl: true,
      }).setView([ECUADOR_CENTER.lat, ECUADOR_CENTER.lng], ECUADOR_CENTER.zoom);

      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(mapPage2);

      L.circleMarker([ECUADOR_CENTER.lat, ECUADOR_CENTER.lng], {
        radius: 7,
        color: "#67e8f9",
        weight: 2,
        fillColor: "#8b5cf6",
        fillOpacity: 0.85,
      }).addTo(mapPage2);

      document.getElementById("map_footer_text").textContent = `Center ${ECUADOR_CENTER.lat.toFixed(4)}, ${ECUADOR_CENTER.lng.toFixed(4)}`;
      return mapPage2;
    }

    function setCurrentPage(index) {
      currentPage = index % 3;
      PAGES.style.transform =
        currentPage === 0 ? "translateX(0%)" :
        currentPage === 1 ? "translateX(-33.333333%)" :
        "translateX(-66.666667%)";
      document.getElementById("page_dot_0").classList.toggle("active", currentPage === 0);
      document.getElementById("page_dot_1").classList.toggle("active", currentPage === 1);
      document.getElementById("page_dot_2").classList.toggle("active", currentPage === 2);

      if (currentPage === 1) {
        ensureMapPage2();
        requestAnimationFrame(() => {
          if (mapPage2) mapPage2.invalidateSize();
          mapWasResized = true;
        });
      }
    }

    function startPageRotation() {
      setCurrentPage(0);
      setInterval(() => setCurrentPage((currentPage + 1) % 3), PAGE_ROTATE_MS);
    }

    async function refreshMetrics() {
      try {
        const r = await fetch("/api/metrics?ts=" + Math.floor(Date.now() / 2000), { cache: "no-store" });
        const d = await r.json();

        document.getElementById("hostname").textContent = d.hostname;
        document.getElementById("ip").textContent = d.ip;
        document.getElementById("uptime").textContent = d.uptime;
        document.getElementById("cpu_usage").textContent = `${Number(d.cpu_usage || 0).toFixed(1)}%`;
        document.getElementById("cpu_temp").textContent = d.cpu_temp === null ? "N/A" : `${Number(d.cpu_temp).toFixed(1)}°C`;
        document.getElementById("load1").textContent = d.load["1m"];
        document.getElementById("load5").textContent = d.load["5m"];
        document.getElementById("load15").textContent = d.load["15m"];
        document.getElementById("throttled").textContent = d.throttled;

        document.getElementById("mem_used").textContent = d.memory.used_mb;
        document.getElementById("mem_total").textContent = d.memory.total_mb;
        document.getElementById("mem_pct").textContent = `${d.memory.percent}%`;

        document.getElementById("disk_used").textContent = d.disk.used_gb;
        document.getElementById("disk_total").textContent = d.disk.total_gb;
        document.getElementById("disk_pct").textContent = `${d.disk.percent}%`;

        const date = new Date((d.timestamp || 0) * 1000);
        document.getElementById("updated").textContent = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });

        setBar("cpu_bar", d.cpu_usage || 0);
        setBar("temp_bar", d.cpu_temp_pct || 0);
        setBar("mem_bar", d.memory.percent || 0);
        setBar("disk_bar", d.disk.percent || 0);
      } catch (err) {
        console.error("metrics refresh failed", err);
      }
    }

    async function refreshBtc() {
      try {
        const r = await fetch("/api/btc?ts=" + Math.floor(Date.now() / 600000), { cache: "no-store" });
        const d = await r.json();

        document.getElementById("btc_source").textContent = d.source || "Unknown";

        if (d.ok && Array.isArray(d.points) && d.points.length > 1) {
          lastGoodBtcPoints = d.points;
          document.getElementById("btc_price").textContent = formatUsd(d.current_price);
          const changeEl = document.getElementById("btc_change");
          const change = Number(d.change_pct || 0);
          changeEl.textContent = `5-day change: ${formatSignedPct(change)}`;
          changeEl.className = "btc-change " + (change >= 0 ? "up" : "down");
          document.getElementById("btc_min").textContent = formatUsd(d.min_price);
          document.getElementById("btc_max").textContent = formatUsd(d.max_price);
          drawChart(d.points);
        } else {
          document.getElementById("btc_price").textContent = "$--";
          const changeEl = document.getElementById("btc_change");
          changeEl.textContent = d.error || "Unable to fetch BTC data";
          changeEl.className = "btc-change warning";
          document.getElementById("btc_min").textContent = "$--";
          document.getElementById("btc_max").textContent = "$--";
          drawChart(lastGoodBtcPoints);
        }

        const updated = new Date((d.updated_at || 0) * 1000);
        const suffix = d.stale ? " · showing cached data" : " · cache 15 min";
        document.getElementById("btc_updated").textContent = `BTC updated ${updated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}${suffix}`;
      } catch (err) {
        console.error("btc refresh failed", err);
      }
    }


    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function renderTrendCards(posts) {
      const list = document.getElementById("trends_list");
      if (!Array.isArray(posts) || posts.length === 0) {
        list.innerHTML = `
          <div class="tweet-card">
            <div class="tweet-head">
              <div class="tweet-user">
                <div class="tweet-name">Sin tendencias disponibles</div>
                <div class="tweet-handle">@ecuador_trends</div>
              </div>
            </div>
            <div class="tweet-text">No se pudieron cargar tendencias relevantes de Ecuador.</div>
            <div class="tweet-actions"><span>Reintentando…</span></div>
          </div>`;
        return;
      }

      list.innerHTML = posts.slice(0, 2).map(post => `
        <div class="tweet-card">
          <div class="tweet-head">
            <div class="tweet-user">
              <div class="tweet-name">${escapeHtml(post.display_name || "Ecuador Trends")}</div>
              <div class="tweet-handle">${escapeHtml(post.handle || "@ecuador_trends")}</div>
            </div>
            <div class="tweet-topic">${escapeHtml(post.topic || "Tendencia")}</div>
          </div>
          <div class="tweet-text">${escapeHtml(post.text || "")}</div>
          <div class="tweet-actions">
            <span>Búsqueda en vivo</span>
            <a class="tweet-link" href="${escapeHtml(post.search_url || "#")}" target="_blank" rel="noopener noreferrer">Abrir en X</a>
          </div>
        </div>`).join("");
    }

    async function refreshEcuadorTrends() {
      try {
        const r = await fetch("/api/ecuador-trends?ts=" + Math.floor(Date.now() / 600000), { cache: "no-store" });
        const d = await r.json();
        renderTrendCards(d.posts || []);
        const updated = new Date((d.updated_at || 0) * 1000);
        const suffix = d.stale ? " · mostrando cache" : " · cache 15 min";
        document.getElementById("trends_updated").textContent = `Tendencias ${updated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}${suffix}`;
      } catch (err) {
        console.error("trend refresh failed", err);
      }
    }


    function formatMbps(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
      const num = Number(value);
      if (num >= 1000) return (num / 1000).toFixed(1) + " Gbps";
      return num.toFixed(num >= 100 ? 0 : 1) + " Mbps";
    }

    function drawSparkline(canvas, points, mode = "percent") {
      const ctx = canvas.getContext("2d");
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      const pad = { top: 6, right: 6, bottom: 6, left: 6 };
      const cw = w - pad.left - pad.right;
      const ch = h - pad.top - pad.bottom;

      ctx.strokeStyle = "rgba(255,255,255,0.07)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.left, pad.top + ch);
      ctx.lineTo(w - pad.right, pad.top + ch);
      ctx.stroke();

      if (!Array.isArray(points) || points.length < 2) {
        ctx.fillStyle = "rgba(255,255,255,0.45)";
        ctx.font = "10px Inter, sans-serif";
        ctx.fillText("sin datos", pad.left + 2, pad.top + 14);
        return;
      }

      const values = points.map(p => Number(p.v || 0));
      let min = Math.min(...values);
      let max = Math.max(...values);

      if (mode === "percent") {
        min = 0;
        max = Math.max(100, max);
      } else if (max === min) {
        max = min + 1;
      }

      const span = Math.max(1, max - min);
      const xFor = (i) => pad.left + (i / (points.length - 1)) * cw;
      const yFor = (value) => pad.top + ((max - value) / span) * ch;

      ctx.beginPath();
      points.forEach((point, i) => {
        const x = xFor(i);
        const y = yFor(Number(point.v || 0));
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });

      const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
      gradient.addColorStop(0, "rgba(103,232,249,0.95)");
      gradient.addColorStop(1, "rgba(139,92,246,0.95)");
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 2;
      ctx.stroke();

      const last = points[points.length - 1];
      ctx.beginPath();
      ctx.arc(xFor(points.length - 1), yFor(Number(last.v || 0)), 2.8, 0, Math.PI * 2);
      ctx.fillStyle = "#eef2ff";
      ctx.fill();
    }

    function renderDOServers(payload) {
      const wrap = document.getElementById("do_servers_wrap");
      const updatedEl = document.getElementById("do_updated");

      if (!payload || !payload.ok || !Array.isArray(payload.servers) || payload.servers.length === 0) {
        wrap.innerHTML = `<div class="server-empty">${escapeHtml((payload && payload.error) || "Sin datos de DigitalOcean.")}</div>`;
        if (updatedEl) {
          const updated = new Date(((payload && payload.updated_at) || 0) * 1000);
          const stamp = isNaN(updated.getTime()) ? "sin datos" : updated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
          updatedEl.textContent = `${stamp} · ${(payload && payload.error) || "Sin configuración"}`;
        }
        return;
      }

      wrap.innerHTML = payload.servers.slice(0, 3).map((server, idx) => `
        <div class="server-row">
          <div class="server-meta">
            <div class="server-name">${escapeHtml(server.name || "Droplet")}</div>
            <div class="server-id">ID ${escapeHtml(server.id || "--")}</div>
            <div class="server-chip-row">
              <span class="server-chip">48 h</span>
              <span class="server-chip">BW pública</span>
            </div>
          </div>

          <div class="mini-metric">
            <div class="mini-label">CPU</div>
            <div class="mini-value">${Number(server.cpu_pct || 0).toFixed(1)}%</div>
            <canvas class="sparkline" id="do_cpu_${idx}"></canvas>
          </div>

          <div class="mini-metric">
            <div class="mini-label">RAM</div>
            <div class="mini-value">${Number(server.ram_pct || 0).toFixed(1)}%</div>
            <canvas class="sparkline" id="do_ram_${idx}"></canvas>
          </div>

          <div class="mini-metric">
            <div class="mini-label">Disco</div>
            <div class="mini-value">${Number(server.disk_pct || 0).toFixed(1)}%</div>
            <canvas class="sparkline" id="do_disk_${idx}"></canvas>
          </div>

          <div class="mini-metric">
            <div class="mini-label">Ancho banda</div>
            <div class="mini-value">${formatMbps(server.bandwidth_mbps || 0)}</div>
            <canvas class="sparkline" id="do_bw_${idx}"></canvas>
          </div>
        </div>`).join("");

      payload.servers.slice(0, 3).forEach((server, idx) => {
        drawSparkline(document.getElementById(`do_cpu_${idx}`), server.series && server.series.cpu, "percent");
        drawSparkline(document.getElementById(`do_ram_${idx}`), server.series && server.series.ram, "percent");
        drawSparkline(document.getElementById(`do_disk_${idx}`), server.series && server.series.disk, "percent");
        drawSparkline(document.getElementById(`do_bw_${idx}`), server.series && server.series.bandwidth, "throughput");
      });

      const updated = new Date((payload.updated_at || 0) * 1000);
      const suffix = payload.stale ? " · mostrando cache" : " · cache 5 min";
      updatedEl.textContent = `DO ${updated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}${suffix}`;
    }

    async function refreshDigitalOcean() {
      try {
        const r = await fetch("/api/digitalocean?ts=" + Math.floor(Date.now() / 300000), { cache: "no-store" });
        const d = await r.json();
        lastDoData = d;
        renderDOServers(d);
      } catch (err) {
        console.error("digitalocean refresh failed", err);
      }
    }

    async function refreshDisplayState() {
      try {
        const r = await fetch("/api/display-state?ts=" + Math.floor(Date.now() / (__DISPLAY_STATE_POLL_SECONDS__ * 1000)), { cache: "no-store" });
        const d = await r.json();
        renderPanelRight(d);
      } catch (err) {
        console.error("display state refresh failed", err);
      }
    }

    window.addEventListener("resize", () => {
      drawChart(lastGoodBtcPoints);
      if (mapPage2 && mapWasResized) mapPage2.invalidateSize();
      if (lastDoData && lastDoData.servers) renderDOServers(lastDoData);
    });

    drawChart([]);
    renderPanelRight({ panel_right: { type: "icon", value: "rocket", title: "Mood", subtitle: "Loading display state..." } });
    ensureMapPage2();
    startPageRotation();
    refreshMetrics();
    refreshBtc();
    refreshDisplayState();
    refreshEcuadorTrends();
    refreshDigitalOcean();
    setInterval(refreshMetrics, 4000);
    setInterval(refreshBtc, 60000);
    setInterval(refreshDisplayState, __DISPLAY_STATE_POLL_SECONDS__ * 1000);
    setInterval(refreshEcuadorTrends, 60000);
    setInterval(refreshDigitalOcean, 60000);
  </script>
</body>
</html>
'''


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html, status=200):
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            html = (
                HTML.replace("__DISPLAY_STATE_POLL_SECONDS__", str(DISPLAY_STATE_POLL_SECONDS))
                .replace("__PAGE_ROTATE_MS__", str(PAGE_ROTATE_SECONDS * 1000))
                                .replace("__ECUADOR_LAT__", str(ECUADOR_CENTER["lat"]))
                .replace("__ECUADOR_LNG__", str(ECUADOR_CENTER["lng"]))
                .replace("__ECUADOR_ZOOM__", str(ECUADOR_CENTER["zoom"]))
            )
            self._send_html(html)
            return

        if self.path.startswith("/api/metrics"):
            self._send_json(get_metrics())
            return

        if self.path.startswith("/api/btc"):
            self._send_json(get_btc_history(days=BTC_DAYS))
            return

        if self.path.startswith("/api/display-state"):
            self._send_json(get_display_state())
            return

        if self.path.startswith("/api/ecuador-trends"):
            self._send_json(get_ecuador_trending_posts())
            return

        if self.path.startswith("/api/digitalocean"):
            self._send_json(get_digitalocean_metrics())
            return

        self._send_json({"error": "Not found"}, status=404)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"PiDashboard listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
