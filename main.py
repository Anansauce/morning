from datetime import date, datetime
import math
import re
import time
import urllib.parse
import random
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RequestException
from wechatpy import WeChatClient
from wechatpy.client.api import WeChatMessage

# timestamp for calculations
today = datetime.now()

# Environment variables (safe reads)
_start_date_env = os.environ.get('START_DATE', '').strip()
start_date = _start_date_env if _start_date_env else None
city = os.environ.get('CITY', '北京')
birthday = os.environ.get('BIRTHDAY', '01-01')

app_id = os.environ.get("APP_ID")
app_secret = os.environ.get("APP_SECRET")
user_id = os.environ.get("USER_ID")
template_id = os.environ.get("TEMPLATE_ID")

def _parse_temp_value(v):
    """Extract integer temperature from various formats; return None on failure."""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return int(math.floor(float(v)))
        s = str(v)
        m = re.search(r'-?\d+\.?\d*', s)
        if not m:
            return None
        return int(math.floor(float(m.group())))
    except Exception:
        return None

def get_weather():
    """Try primary provider (autodev openspeech) via HTTPS, then wttr.in, then OpenWeatherMap (if WEATHER_API_KEY).
    Returns: (desc, temp, min_temp, max_temp)
    """
    city_q = urllib.parse.quote_plus(city)

    # session with retries
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    def try_primary():
        url = f"https://autodev.openspeech.cn/csp/api/v2.1/weather?openId=aiuicus&clientType=android&sign=android&city={city_q}"
        try:
            r = session.get(url, timeout=10)
            print("[weather] primary status:", r.status_code)
            print("[weather] primary raw (truncated):", r.text[:1500])
            r.raise_for_status()
            res = r.json()
        except RequestException as e:
            print("[weather] primary request failed:", e)
            return None
        except ValueError as e:
            print("[weather] primary invalid json:", e)
            return None

        # API-level error (e.g., sign invalid)
        if isinstance(res, dict) and res.get("code") not in (None, 0):
            print("[weather] primary API returned error:", res)
            return None

        # expected structure: data.list[0]
        node = None
        try:
            if isinstance(res, dict) and 'data' in res and isinstance(res['data'], dict) and 'list' in res['data'] and res['data']['list']:
                node = res['data']['list'][0]
            elif isinstance(res, dict) and 'list' in res and res['list']:
                node = res['list'][0]
            elif isinstance(res, dict) and 'weather' in res and isinstance(res['weather'], list) and res['weather']:
                node = res['weather'][0]
        except Exception:
            node = None

        if not node:
            print("[weather] primary unexpected payload:", res)
            return None

        desc = node.get('weather') or node.get('description') or node.get('text') or '晴'
        temp = _parse_temp_value(node.get('temp') or node.get('temperature') or node.get('now') or node.get('tem')) or 20

        min_candidates = ('low', 'lowTemp', 'tem_low', 'min_temp', 'min', 'temp_min', 'temperatureLow')
        max_candidates = ('high', 'highTemp', 'tem_high', 'max_temp', 'max', 'temp_max', 'temperatureHigh')

        min_t = None
        for k in min_candidates:
            if k in node:
                min_t = _parse_temp_value(node.get(k))
                if min_t is not None:
                    break

        max_t = None
        for k in max_candidates:
            if k in node:
                max_t = _parse_temp_value(node.get(k))
                if max_t is not None:
                    break

        # parse ranges like "20/28" or "20~28"
        if (min_t is None or max_t is None):
            for k in ('temperature','temp_range','range','weatherRange','tem'):
                v = node.get(k)
                if isinstance(v, str) and any(sep in v for sep in ('/', '~', '到', '-', '–', '—')):
                    parts = re.split(r'[\/~到\-–—]', v)
                    if len(parts) >= 2:
                        p0 = _parse_temp_value(parts[0]); p1 = _parse_temp_value(parts[1])
                        if p0 is not None and p1 is not None:
                            min_t, max_t = min(p0,p1), max(p0,p1)
                            break

        if min_t is None: min_t = temp
        if max_t is None: max_t = temp
        return desc, temp, min_t, max_t

    def try_wttr():
        url = f"https://wttr.in/{city_q}?format=j1"
        try:
            r = session.get(url, timeout=10)
            print("[weather] wttr status:", r.status_code)
            print("[weather] wttr raw (truncated):", r.text[:1500])
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            print("[weather] wttr failed:", e)
            return None
        try:
            cur = j.get('current_condition', [{}])[0]
            desc = cur.get('weatherDesc', [{'value':'晴'}])[0].get('value','晴')
            temp = int(float(cur.get('temp_C', 20)))
            daily = j.get('weather', [])
            if daily:
                min_t = int(float(daily[0].get('mintempC', temp)))
                max_t = int(float(daily[0].get('maxtempC', temp)))
            else:
                min_t = max_t = temp
            return desc, temp, min_t, max_t
        except Exception as e:
            print("[weather] wttr parse failed:", e)
            return None

    def try_openweathermap():
        key = os.environ.get("WEATHER_API_KEY")
        if not key:
            print("[weather] no WEATHER_API_KEY for OpenWeatherMap fallback")
            return None
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_q}&appid={key}&units=metric&lang=zh_cn"
        try:
            r = session.get(url, timeout=10)
            print("[weather] owm status:", r.status_code)
            print("[weather] owm raw (truncated):", r.text[:1500])
            r.raise_for_status()
            j = r.json()
            desc = j.get('weather',[{}])[0].get('description','晴')
            temp = int(math.floor(float(j.get('main',{}).get('temp',20))))
            min_t = int(math.floor(float(j.get('main',{}).get('temp_min', temp))))
            max_t = int(math.floor(float(j.get('main',{}).get('temp_max', temp))))
            return desc, temp, min_t, max_t
        except Exception as e:
            print("[weather] owm failed:", e)
            return None

    # try providers in order
    for fn in (try_primary, try_wttr, try_openweathermap):
        r = fn()
        if r:
            return r

    print("[weather] all providers failed, using defaults")
    return "晴", 20, 20, 20

def get_count():
    if not start_date:
        print("START_DATE is not set; returning 0 for love days.")
        return 0
    try:
        delta = today - datetime.strptime(start_date, "%Y-%m-%d")
        return delta.days
    except Exception as e:
        print("Error parsing START_DATE:", e)
        return 0

def get_birthday():
    try:
        next_birthday = datetime.strptime(str(date.today().year) + "-" + birthday, "%Y-%m-%d")
        if next_birthday < datetime.now():
            next_birthday = next_birthday.replace(year=next_birthday.year + 1)
        return (next_birthday - today).days
    except Exception as e:
        print("Error parsing BIRTHDAY:", e)
        return 0

def get_words():
    try:
        words = requests.get("https://api.shadiao.pro/chp", timeout=10)
        if words.status_code != 200:
            return get_words()
        return words.json().get('data', {}).get('text', '')
    except Exception as e:
        print("get_words failed:", e)
        return ""

def get_random_color():
    return "#%06x" % random.randint(0, 0xFFFFFF)

# send message
client = WeChatClient(app_id, app_secret)
wm = WeChatMessage(client)

wea, temperature, min_temperature, max_temperature = get_weather()

data = {
    "weather": {"value": wea},
    "temperature": {"value": temperature},
    "min_temperature": {"value": min_temperature},
    "max_temperature": {"value": max_temperature},
    "love_days": {"value": get_count()},
    "birthday_left": {"value": get_birthday()},
    "words": {"value": get_words(), "color": get_random_color()},
}

try:
    res = wm.send_template(user_id, template_id, data)
    print(res)
except Exception as e:
    print("Failed to send template message:", e)
