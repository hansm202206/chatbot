import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image
import io

# --- 0. 설정 및 보안 (Secrets 필수 확인) ---
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
    """네이버 장소 검색(local.json)을 사용하여 맛집 정보를 가져옵니다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return "네이버 API 키가 설정되지 않았습니다. Secrets 설정을 확인해주세요."
    
    # 검색 정확도를 위해 불필요한 수식어 제거
    clean_query = query.replace("맛집", "").replace("추천해줘", "").replace("추천", "").strip()
    
    # 핵심: local.json 경로를 사용해야 식당 데이터가 나옵니다.
    url = f"https://openapi.naver.com/v1/search/local.json?query={clean_query}&display=5&sort=comment"
    
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        
        if not items:
            return f"'{clean_query}'에 대한 장소 검색 결과가 없습니다. 네이버 개발자 센터에서 '지역' API 권한이 활성화되어 있는지 확인이 필요합니다."
        
        results = [f"🍴 '{clean_query}' 관련 네이버 검색 결과입니다:"]
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '') # HTML 태그 제거
            address = item['address']
            category = item['category']
            results.append(f"- **{title}** ({category})\n  📍 주소: {address}")
            
        return "\n\n".join(results)
    except Exception as e:
        return f"네이버 검색 중 오류 발생: {str(e)}"

def search_youtube(query: str):
    """유튜브 검색 링크를 제공합니다."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return f"📺 유튜브 검색 결과: {url}"

def register_reminder(time_str: str, content: str):
    """리마인더 저장."""
    c = conn.cursor()
    c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
    conn.commit()
    return f"✅ {time_str}에 '{content}'를 등록했습니다."

# --- 3. Gemini 1.5 Flash 설정 ---
genai.configure(api_key=GEMINI_API_KEY)

# 구글 검색 대신 네이버 함수를 도구로 사용
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', 
    tools=[get_current_time, get_weather, search_naver, search_youtube, register_reminder],
    system_instruction="""당신은 실시간 정보를 네이버에서 찾아주는 만능 비서입니다.
    - 맛집이나 장소를 물어보면 반드시 'search_naver' 함수를 호출하세요.
    - 검색 결과가 나오면 주소와 특징을 정리해서 사용자에게 친절하게 알려주세요.
    - 사진을 올리면 사진 내용을 분석하고 관련된 정보를 검색해서 대답하세요."""
)

# --- 4. 대화 세션 관리 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)

# --- 5. UI 구성 ---
st.title("🚀 슈퍼 네이버 AI 비서")

with st.sidebar:
    st.header("⏰ 리마인더")
    reminders = conn.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC").fetchall()
    for dt, msg in reminders:
        st.write(f"🔔 **{dt}**\n{msg}")

uploaded_file = st.file_uploader("🖼️ 사진 분석", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, use_container_width=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("왕십리 곱창 맛집 알려줘!"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("정보를 찾는 중..."):
            try:
                if uploaded_file:
                    img = Image.open(uploaded_file)
                    response = st.session_state.chat_session.send_message([prompt, img])
                else:
                    response = st.session_state.chat_session.send_message(prompt)
                
                res_text = response.text
                st.markdown(res_text)
                st.session_state.messages.append({"role": "assistant", "content": res_text})
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")