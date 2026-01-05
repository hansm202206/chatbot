import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image

# --- 0. Streamlit Secrets에서 키 불러오기 ---
# Streamlit Cloud의 Settings -> Secrets에 GEMINI_API_KEY와 WEATHER_API_KEY가 등록되어 있어야 합니다.
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "") # 없으면 빈값

st.set_page_config(page_title="슈퍼 만능 AI", page_icon="🚀", layout="centered")

# --- 1. DB 및 시간 설정 ---
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
    """현재 한국 시간을 확인합니다."""
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def get_weather(city_name: str):
    """특정 도시의 실시간 날씨를 가져옵니다."""
    if not WEATHER_API_KEY: return "날씨 API 키가 설정되지 않았습니다."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"📍 {city_name}: {res['weather'][0]['description']}, 온도 {res['main']['temp']}°C"
        return f"'{city_name}' 도시를 찾을 수 없습니다."
    except: return "날씨 정보를 가져오는 중 오류가 발생했습니다."

def search_youtube(query: str):
    """주제와 관련된 유튜브 검색 링크를 제공합니다."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return f"📺 '{query}' 관련 유튜브 결과입니다: {url}"

# --- 3. Gemini 설정 (Gemini 1.5 Flash 모델 적용) ---
genai.configure(api_key=GEMINI_API_KEY)

# 말씀하신 대로 최신 고성능 모델인 gemini-1.5-flash를 사용합니다.
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', 
    tools=[get_current_time, get_weather, search_youtube],
    system_instruction="당신은 사진 분석, 날씨, 유튜브 추천을 수행하는 만능 AI 비서입니다. 과거 대화를 기억하며 친절하게 대답하세요."
)

# --- 4. 대화 로직 ---
if "messages" not in st.session_state:
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 10")
    db_rows = c.fetchall()[::-1]
    st.session_state.messages = [{"role": ("assistant" if r=='model' else 'user'), "content": c} for r, c in db_rows]
    st.session_state.chat_session = model.start_chat(
        history=[{"role": r, "parts": [c]} for r, c in db_rows],
        enable_automatic_function_calling=True
    )

# --- 5. UI 구성 ---
st.title("🚀 슈퍼 만능 AI 비서")

# 이미지 업로드
uploaded_file = st.file_uploader("🖼️ 사진을 분석해 드릴까요?", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, caption="업로드된 이미지", use_container_width=True)

# 채팅 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 입력 처리
if prompt := st.chat_input("무엇이든 물어보세요!"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # DB 저장
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("user", prompt, datetime.now()))
    conn.commit()

    with st.chat_message("assistant"):
        with st.spinner("생각 중..."):
            if uploaded_file:
                img = Image.open(uploaded_file)
                # 이미지와 텍스트 함께 전송
                response = st.session_state.chat_session.send_message([prompt, img])
            else:
                response = st.session_state.chat_session.send_message(prompt)
            
            full_res = response.text
            st.markdown(full_res)
            st.session_state.messages.append({"role": "assistant", "content": full_res})
            
            # AI 응답 DB 저장
            c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("model", full_res, datetime.now()))
            conn.commit()