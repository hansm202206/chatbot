import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image
import io

# --- 0. 설정 및 보안 (Secrets) ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
NAVER_CLIENT_ID = st.secrets.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = st.secrets.get("NAVER_CLIENT_SECRET", "")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")

st.set_page_config(page_title="슈퍼 네이버 AI 비서", page_icon="🚀", layout="wide")

# --- 1. 시간 및 데이터베이스 설정 ---
KST = timezone(timedelta(hours=9))

def init_db():
    conn = sqlite3.connect("super_bot.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS chat_history (role TEXT, content TEXT, timestamp DATETIME)")
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    conn.commit()
    return conn

conn = init_db()

# --- 2. AI 도구(Tools) 정의 ---

def get_current_time():
    """현재 한국의 날짜와 시간을 확인합니다."""
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def get_weather(city_name: str):
    """특정 도시의 실시간 날씨 정보를 가져옵니다."""
    if not WEATHER_API_KEY: return "날씨 API 키가 없습니다."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"📍 {city_name}: {res['weather'][0]['description']}, 온도 {res['main']['temp']}°C"
        return f"'{city_name}'을 찾을 수 없습니다."
    except: return "날씨 조회 중 오류 발생."

def search_naver(query: str):
    """네이버 검색을 통해 실시간 뉴스나 맛집 정보를 가져옵니다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return "네이버 API 키가 설정되지 않았습니다."
    
    # 뉴스 검색과 지역(맛집) 검색을 동시에 수행
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=5"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        if not items:
            return f"'{query}'에 대한 네이버 검색 결과가 없습니다."
        
        results = [f"제목: {item['title']}, 주소: {item['address']}, 링크: {item['link']}" for item in items]
        return "\n".join(results)
    except:
        return "네이버 검색 중 오류가 발생했습니다."

def search_youtube(query: str):
    """유튜브 검색 링크를 제공합니다."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return f"📺 유튜브 검색 결과: {url}"

def register_reminder(time_str: str, content: str):
    """리마인더 저장. 형식: 'YYYY-MM-DD HH:MM'"""
    c = conn.cursor()
    c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
    conn.commit()
    return f"✅ {time_str}에 '{content}'를 리마인더에 등록했습니다."

# --- 3. Gemini 1.5 Flash 설정 (네이버 도구 적용) ---
genai.configure(api_key=GEMINI_API_KEY)

# 구글 검색(google_search)을 제거하고 네이버 함수(search_naver)를 포함
my_tools = [get_current_time, get_weather, search_naver, search_youtube, register_reminder]

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', 
    tools=my_tools,
    system_instruction="""당신은 실시간 검색이 가능한 만능 AI 비서입니다.
    - 맛집, 뉴스, 장소 질문에는 반드시 'search_naver' 도구를 사용하여 정보를 가져오세요.
    - 검색 결과에서 HTML 태그(<b> 등)는 제거하고 깔끔하게 정리해 대답하세요.
    - 사진 분석도 가능하며, 항상 친절하게 한국어로 답변하세요."""
)

# --- 4. 대화 세션 관리 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)

# --- 5. UI 구성 ---
st.title("🚀 슈퍼 네이버 AI 비서")

# 사이드바 리마인더
with st.sidebar:
    st.header("⏰ 리마인더")
    reminders = conn.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC").fetchall()
    for dt, msg in reminders:
        st.write(f"🔔 **{dt}**\n{msg}")

uploaded_file = st.file_uploader("🖼️ 사진 분석", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, use_container_width=True)

# 채팅 출력 및 입력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("검색내용 입력해주세요."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("네이버 검색 중..."):
            try:
                if uploaded_file:
                    img = Image.open(uploaded_file)
                    response = st.session_state.chat_session.send_message([prompt, img])
                else:
                    response = st.session_state.chat_session.send_message(prompt)
                
                res_text = response.text
                st.markdown(res_text)
                st.session_state.messages.append({"role": "assistant", "content": res_text})
                
                # 맛집 키워드 시 지도 표시
                if "맛집" in prompt:
                    st.map(pd.DataFrame({'lat': [37.5612], 'lon': [127.0385]})) # 왕십리역 좌표 샘플
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")