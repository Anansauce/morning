from datetime import date, datetime
import math
from wechatpy import WeChatClient
from wechatpy.client.api import WeChatMessage
import requests
import os
import random
import re

today = datetime.now()
_start_date_env = os.environ.get('START_DATE', '').strip()
start_date = _start_date_env if _start_date_env else None
city = os.environ.get('CITY', '北京')
birthday = os.environ.get('BIRTHDAY', '01-01')

app_id = os.environ.get("APP_ID")
app_secret = os.environ.get("APP_SECRET")
user_id = os.environ.get("USER_ID")
template_id = os.environ.get("TEMPLATE_ID")

def _parse_temp_value(v):
    """尝试从各种字符串/数字中提取温度整数，失败返回 None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(math.floor(float(v)))
    s = str(v)
    # 找到第一个可能的带负号的整数或小数
    m = re.search(r'-?\d+\.?\d*', s)
    if not m:
        return None
    try:
        return int(math.floor(float(m.group())))
    except Exception:
        return None

def get_weather():
    url = f"http://autodev.openspeech.cn/csp/api/v2.1/weather?openId=aiuicus&clientType=android&sign=android&city={city}"
    try:
        res = requests.get(url, timeout=10).json()
    except Exception as e:
        print("Weather API request failed:", e)
        return "晴", 20, 20, 20

    # 临时打印响应以便确认字段（调试用，确认字段后可以移除）
    print("Weather API response:", res)

    # 标准路径： data.list[0]
    if isinstance(res, dict) and 'data' in res and isinstance(res['data'], dict) and 'list' in res['data'] and len(res['data']['list']) > 0:
        weather = res['data']['list'][0]

        # 当前天气描述
        wea = weather.get('weather') or weather.get('description') or '晴'

        # 尝试解析当前温度
        temp = _parse_temp_value(weather.get('temp') or weather.get('temperature') or weather.get('now') or weather.get('tem')) or 20

        # 兼容多个可能的最低/最高字段名
        min_keys = ('low', 'lowTemp', 'tem_low', 'temperatureLow', 'min_temp', 'min', 'tem1', 'temp_min')
        max_keys = ('high', 'highTemp', 'tem_high', 'temperatureHigh', 'max_temp', 'max', 'tem2', 'temp_max')

        min_temp = None
        for k in min_keys:
            if k in weather:
                min_temp = _parse_temp_value(weather.get(k))
                if min_temp is not None:
                    break

        max_temp = None
        for k in max_keys:
            if k in weather:
                max_temp = _parse_temp_value(weather.get(k))
                if max_temp is not None:
                    break

        # 一些接口可能把最高最低放在 range 字段或以字符串形式提供，例如 "20/28"、"20℃~28℃"
        if (min_temp is None or max_temp is None):
            # 尝试在某些常见字符串字段中解析
            for k in ('temperature', 'temp_range', 'range', 'weatherRange', 'tem'):
                v = weather.get(k)
                if isinstance(v, str) and ('/' in v or '~' in v or '到' in v):
                    parts = re.split(r'[\/~到\-–—]', v)
                    if len(parts) >= 2:
                        p0 = _parse_temp_value(parts[0])
                        p1 = _parse_temp_value(parts[1])
                        if p0 is not None and p1 is not None:
                            min_temp = p0 if p0 <= p1 else p1
                            max_temp = p1 if p1 >= p0 else p0
                            break

        # 兜底：如果还没有解析到，就用当前温度
        if min_temp is None:
            min_temp = temp
        if max_temp is None:
            max_temp = temp

        return wea, temp, min_temp, max_temp

    # 非预期响应（如签名无效），打印并返回默认
    print("Unexpected weather API response:", res)
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
