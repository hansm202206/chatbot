import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image

# --- 0. 설정 및 보안 ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
NAVER_CLIENT_ID = st.secrets.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = st.secrets.get("NAVER_CLIENT_SECRET", "")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")

st.set_page_config(page_title="AI 비서", page_icon="🤖", layout="wide")

# --- 1. 유틸리티 및 DB 설정 ---
KST = timezone(timedelta(hours=9))
def init_db():
    conn = sqlite3.connect("super_bot.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    conn.commit()
    return conn
conn = init_db()

def transform_coords(x, y):
    try: return float(y) / 10000000, float(x) / 10000000
    except: return 37.5612, 127.0385

def make_naver_map_link(title, address):
    clean_title = title.replace('<b>', '').replace('</b>', '')
    return f"https://map.naver.com/v5/search/{clean_title}%20{address}"

# --- 2. 통합 도구(Tools) 정의 ---
def search_naver(query: str):
    """네이버에서 장소 정보를 검색합니다."""
    if not NAVER_CLIENT_ID: return "네이버 API 설정 필요", []
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=5"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        if not items: return "검색 결과가 없습니다.", []
        
        info_list = []
        locations = []
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            link = make_naver_map_link(title, item['address'])
            info_list.append(f"📍 **{title}** ({item['category']})\n- 주소: {item['address']}\n- [🔗 네이버 지도로 보기]({link})")
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon})
        return "\n\n".join(info_list), locations
    except: return "검색 오류 발생", []

def get_weather(city_name: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    res = requests.get(url).json()
    return f"📍 {city_name}: {res['main']['temp']}°C, {res['weather'][0]['description']}" if res.get("cod")==200 else "날씨 정보 없음"

def search_youtube(query: str):
    return f"📺 유튜브 검색 결과: https://www.youtube.com/results?search_query={query.replace(' ', '+')}"

# --- 3. Gemini 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[search_naver, get_weather, search_youtube],
    system_instruction="""당신은 친절한 AI 비서입니다. 
    1. 장소 검색 시 'search_naver' 결과를 바탕으로 깔끔하게 리스트 형태로 대답하세요.
    2. 링크는 반드시 '[🔗 네이버 지도로 보기](URL)' 형식을 유지하세요.
    3. 사용자의 질문 의도에 맞는 장소만 선별하여 답변하세요."""
)

# --- 4. UI 구성 ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🚀 AI 비서")

with st.sidebar:
    st.header("⏰ 리마인더")
    rem_list = conn.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC").fetchall()
    for dt, msg in rem_list: st.write(f"🔔 {dt}: {msg}")

uploaded_file = st.file_uploader("🖼️ 사진 분석", type=["jpg", "png", "jpeg"])
if uploaded_file: st.image(uploaded_file, use_container_width=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "map" in msg and msg["map"] is not None: st.map(msg["map"])

if prompt := st.chat_input("궁금한 것을 물어보세요!"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        # 지도 좌표 수동 추출 로직
        info_text, locations = "", []
        if any(k in prompt for k in ["어디", "맛집", "장소", "근처"]):
            info_text, locations = search_naver(prompt)
        
        input_content = [prompt, Image.open(uploaded_file)] if uploaded_file else prompt
        response = st.session_state.chat_session.send_message(input_content)
        
        st.markdown(response.text)
        map_df = pd.DataFrame(locations) if locations else None
        if map_df is not None: st.map(map_df)
        
        st.session_state.messages.append({"role": "assistant", "content": response.text, "map": map_df})