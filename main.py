from datetime import date, datetime
import math
from wechatpy import WeChatClient
from wechatpy.client.api import WeChatMessage
import requests
import os
import random

today = datetime.now()
start_date = os.environ.get('START_DATE', '2020-01-01')
city = os.environ.get('CITY', '北京')
birthday = os.environ.get('BIRTHDAY', '01-01')

app_id = os.environ.get("APP_ID")
app_secret = os.environ.get("APP_SECRET")
user_id = os.environ.get("USER_ID")
template_id = os.environ.get("TEMPLATE_ID")

def get_weather():
    url = f"http://autodev.openspeech.cn/csp/api/v2.1/weather?openId=aiuicus&clientType=android&sign=android&city={city}"
    try:
        res = requests.get(url, timeout=10).json()
    except Exception as e:
        print("Weather API request failed:", e)
        return "晴", 20

    if isinstance(res, dict) and 'data' in res and isinstance(res['data'], dict) and 'list' in res['data'] and len(res['data']['list']) > 0:
        weather = res['data']['list'][0]
        wea = weather.get('weather', '晴')
        try:
            temp = math.floor(float(weather.get('temp', 20)))
        except Exception:
            temp = 20
        return wea, temp

    print("Unexpected weather API response:", res)
    return "晴", 20

def get_count():
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
wea, temperature = get_weather()
data = {
    "weather": {"value": wea},
    "temperature": {"value": temperature},
    "love_days": {"value": get_count()},
    "birthday_left": {"value": get_birthday()},
    "words": {"value": get_words(), "color": get_random_color()},
}
try:
    res = wm.send_template(user_id, template_id, data)
    print(res)
except Exception as e:
    print("Failed to send template message:", e)
