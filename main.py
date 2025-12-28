from datetime import date, datetime
import math
from wechatpy import WeChatClient
from wechatpy.client.api import WeChatMessage
import requests
import os
import random
import re

# Current timestamp for calculations
today = datetime.now()

# Read environment variables with safe defaults
_start_date_env = os.environ.get('START_DATE', '').strip()
start_date = _start_date_env if _start_date_env else None
city = os.environ.get('CITY', '北京')
birthday = os.environ.get('BIRTHDAY', '01-01')

app_id = os.environ.get('APP_ID')
app_secret = os.environ.get('APP_SECRET')
user_id = os.environ.get('USER_ID')
template_id = os.environ.get('TEMPLATE_ID')


def _parse_temp_value(v):
    """Try to extract an integer temperature from various formats.
    Returns int or None on failure.
    """
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
    url = f"http://autodev.openspeech.cn/csp/api/v2.1/weather?openId=aiuicus&clientType=android&sign=android&city={city}"
    try:
        r = requests.get(url, timeout=10)
    except Exception as e:
        print("Weather HTTP request failed:", e)
        return "晴", 20, 20, 20

    # Debug prints to inspect response structure in Actions logs. Remove after confirming.
    print("Weather HTTP status:", r.status_code)
    print("Weather raw response:", r.text)

    try:
        res = r.json()
    except Exception as e:
        print("Failed to decode weather JSON:", e)
        return "晴", 20, 20, 20

    # If API returns an error code, print and return defaults
    if isinstance(res, dict) and res.get('code') not in (None, 0):
        print("Weather API returned error code:", res)
        return "晴", 20, 20, 20

    # Find weather nodes in common positions
    nodes = []
    if isinstance(res, dict):
        if 'data' in res and isinstance(res['data'], dict) and 'list' in res['data']:
            nodes = res['data']['list']
        elif 'weather' in res and isinstance(res['weather'], list):
            nodes = res['weather']
        elif 'result' in res:
            rnode = res['result']
            if isinstance(rnode, list):
                nodes = rnode
            else:
                nodes = [rnode]

    if not nodes:
        print("No weather nodes found in response:", res)
        return "晴", 20, 20, 20

    weather = nodes[0]

    wea = weather.get('weather') or weather.get('description') or weather.get('text') or '晴'

    temp = _parse_temp_value(weather.get('temp') or weather.get('temperature') or weather.get('now') or weather.get('tem')) or 20

    min_candidates = ('low', 'lowTemp', 'tem_low', 'min_temp', 'min', 'temp_min', 'temperatureLow')
    max_candidates = ('high', 'highTemp', 'tem_high', 'max_temp', 'max', 'temp_max', 'temperatureHigh')

    min_temp = None
    for k in min_candidates:
        if k in weather:
            min_temp = _parse_temp_value(weather.get(k))
            if min_temp is not None:
                break

    max_temp = None
    for k in max_candidates:
        if k in weather:
            max_temp = _parse_temp_value(weather.get(k))
            if max_temp is not None:
                break

    # Try parse ranges like "20/28" or "20~28"
    if (min_temp is None or max_temp is None):
        for k in ('temperature', 'temp_range', 'range', 'weatherRange', 'tem'):
            v = weather.get(k)
            if isinstance(v, str) and any(sep in v for sep in ('/', '~', '到', '—', '-')):
                parts = re.split(r'[\/~到\-–—]', v)
                if len(parts) >= 2:
                    p0 = _parse_temp_value(parts[0])
                    p1 = _parse_temp_value(parts[1])
                    if p0 is not None and p1 is not None:
                        min_temp = min(p0, p1)
                        max_temp = max(p0, p1)
                        break

    if min_temp is None:
        min_temp = temp
    if max_temp is None:
        max_temp = temp

    return wea, temp, min_temp, max_temp


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
