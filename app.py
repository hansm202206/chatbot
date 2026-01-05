import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image
import io

# --- 0. 설정 및 보안 (Secrets) ---
# Streamlit Cloud의 Settings -> Secrets에 아래 키들이 등록되어 있어야 합니다.
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")
NEWS_API = st.secrets.get("NEWS_API", "")

st.set_page_config(page_title="슈퍼 만능 AI 비서", page_icon="🚀", layout="centered")

# --- 1. 시간 및 데이터베이스 설정 ---
KST = timezone(timedelta(hours=9))

def init_db():
    conn = sqlite3.connect("super_bot.db", check_same_thread=False)
    c = conn.cursor()
    # 대화 기록 테이블 (영구 기억용)
    c.execute("CREATE TABLE IF NOT EXISTS chat_history (role TEXT, content TEXT, timestamp DATETIME)")
    # 리마인더 테이블
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
    if not WEATHER_API_KEY:
        return "날씨 API 키가 설정되지 않았습니다. 관리자에게 문의하세요."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"📍 {city_name}: {res['weather'][0]['description']}, 온도 {res['main']['temp']}°C, 습도 {res['main']['humidity']}%"
        return f"'{city_name}' 도시를 찾을 수 없습니다. 영문 도시명을 사용해 보세요."
    except:
        return "날씨 정보를 가져오는 중 오류가 발생했습니다."

def search_youtube(query: str):
    """주제와 관련된 유튜브 동영상 검색 링크를 제공합니다."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return f"📺 '{query}' 관련 유튜브 검색 결과입니다: {url}"

def register_reminder(time_str: str, content: str):
    """알림 또는 리마인더를 저장합니다. 형식: 'YYYY-MM-DD HH:MM'"""
    c = conn.cursor()
    c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
    conn.commit()
    return f"✅ 확인되었습니다. {time_str}에 '{content}'라고 기억해둘게요."

# --- 3. Gemini 1.5 Flash 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[get_current_time, get_weather, search_youtube, register_reminder],
    system_instruction="""당신은 사진 분석, 날씨 조회, 유튜브 추천이 가능한 만능 AI 비서입니다.
    사용자와의 이전 대화 내용을 DB에서 불러와 모두 기억하고 있으며, 이를 바탕으로 친절하고 똑똑하게 대답합니다.
    이미지가 업로드되면 이미지의 내용을 상세히 분석해주고, 시간이나 날씨 질문에는 반드시 도구를 사용하세요."""
)

# --- 4. 대화 기록 로드 및 세션 관리 ---
if "messages" not in st.session_state:
    c = conn.cursor()
    # 최근 대화 15개를 불러와 맥락 유지
    c.execute("SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 15")
    db_rows = c.fetchall()[::-1]
    
    st.session_state.messages = [{"role": ("assistant" if r=='model' else 'user'), "content": c} for r, c in db_rows]
    st.session_state.chat_session = model.start_chat(
        history=[{"role": r, "parts": [c]} for r, c in db_rows],
        enable_automatic_function_calling=True
    )

# --- 5. UI 화면 구성 ---
st.title("🚀 슈퍼 만능 AI 비서")
st.write("당신을 위한 지식, 사진 분석, 생활 비서 서비스를 제공합니다.")

# 사이드바: 리마인더 및 관리자 모드
with st.sidebar:
    st.header("⏰ 예정된 리마인더")
    c = conn.cursor()
    c.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC")
    reminders = c.fetchall()
    if reminders:
        for dt, msg in reminders:
            st.write(f"🔔 **{dt}**\n{msg}")
            st.divider()
    else:
        st.caption("등록된 리마인더가 없습니다.")
    
    st.divider()
    if st.checkbox("🔍 관리자 모드: DB 데이터 확인"):
        st.subheader("💬 전체 대화 로그")
        logs = conn.execute("SELECT role, content, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT 30").fetchall()
        st.dataframe(logs) # 표 형태로 깔끔하게 보기

# 이미지 업로드 섹션
uploaded_file = st.file_uploader("🖼️ 분석할 사진을 올려주세요", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, caption="현재 업로드된 이미지", use_container_width=True)

# 채팅 창 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 메시지 입력 및 처리
if prompt := st.chat_input("무엇이든 물어보세요! (예: 서울 날씨 어때?, 이 사진 설명해줘)"):
    # 1. 사용자 메시지 표시 및 DB 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    c = conn.cursor()
    now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("user", prompt, now_str))
    conn.commit()

    # 2. AI 응답 생성
    with st.chat_message("assistant"):
        with st.spinner("AI가 생각 중입니다..."):
            try:
                if uploaded_file:
                    img = Image.open(uploaded_file)
                    response = st.session_state.chat_session.send_message([prompt, img])
                else:
                    response = st.session_state.chat_session.send_message(prompt)
                
                full_res = response.text
                st.markdown(full_res)
                
                # 3. AI 응답 저장
                st.session_state.messages.append({"role": "assistant", "content": full_res})
                c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("model", full_res, now_str))
                conn.commit()
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")