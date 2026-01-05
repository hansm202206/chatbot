import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd # 지도 데이터 처리를 위해 추가
from datetime import datetime, timedelta, timezone
from PIL import Image
import io

# --- 0. 설정 및 보안 (Secrets) ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")
NEWS_API = st.secrets.get("NEWS_API", "")

st.set_page_config(page_title="슈퍼 만능 AI 비서", page_icon="🚀", layout="wide") # 지도를 위해 wide 모드 권장

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
    if not WEATHER_API_KEY:
        return "날씨 API 키가 설정되지 않았습니다."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"📍 {city_name}: {res['weather'][0]['description']}, 온도 {res['main']['temp']}°C, 습도 {res['main']['humidity']}%"
        return f"'{city_name}' 도시를 찾을 수 없습니다."
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

# --- 3. Gemini 1.5 Flash 설정 (뉴스/맛집 검색 도구 추가) ---
genai.configure(api_key="")

# google_search 도구를 추가하여 실시간 뉴스 및 장소 검색이 가능하게 합니다.
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', 
    tools=[
        get_current_time, 
        get_weather, 
        search_youtube, 
        register_reminder,
        {"google_search": {}} # 실시간 웹 검색 도구 추가
    ],
    system_instruction="""당신은 사진 분석, 실시간 뉴스 검색, 맛집 추천이 가능한 만능 AI 비서입니다.
    - 실시간 정보나 뉴스 질문에는 반드시 구글 검색 도구를 사용하여 최신 정보를 요약하세요.
    - 맛집이나 장소를 추천할 때는 주소, 특징, 평점 등을 상세히 알려주세요.
    - 사용자와의 이전 대화 내용을 기억하며 친절하게 대답하세요."""
)

# --- 4. 대화 기록 로드 및 세션 관리 ---
if "messages" not in st.session_state:
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 15")
    db_rows = c.fetchall()[::-1]
    st.session_state.messages = [{"role": ("assistant" if r=='model' else 'user'), "content": c} for r, c in db_rows]
    st.session_state.chat_session = model.start_chat(
        history=[{"role": r, "parts": [c]} for r, c in db_rows],
        enable_automatic_function_calling=True
    )

# --- 5. UI 화면 구성 ---
st.title("🚀 슈퍼 만능 AI 비서")

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
        st.dataframe(logs)

uploaded_file = st.file_uploader("🖼️ 분석할 사진을 올려주세요", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, caption="업로드된 이미지", use_container_width=True)

# 채팅 출력부
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 메시지 입력 및 처리
if prompt := st.chat_input("무엇이든 물어보세요! (예: 강남역 맛집 추천해줘, 오늘 주요 뉴스 뭐야?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    c = conn.cursor()
    now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("user", prompt, now_str))
    conn.commit()

    with st.chat_message("assistant"):
        with st.spinner("최신 정보를 가져오는 중입니다..."):
            try:
                if uploaded_file:
                    img = Image.open(uploaded_file)
                    response = st.session_state.chat_session.send_message([prompt, img])
                else:
                    response = st.session_state.chat_session.send_message(prompt)
                
                full_res = response.text
                st.markdown(full_res)
                
                # [전문가 기능] 맛집/장소 언급 시 간이 지도 표시 (위경도가 텍스트에 포함될 경우 자동 매핑)
                # 여기서는 시각적 재미를 위해 맛집 키워드가 있을 때 지도를 생성하는 예시를 보여줍니다.
                if "맛집" in prompt or "추천" in prompt:
                    st.info("📍 주변 지역의 주요 포인트를 확인하세요.")
                    # 실제 서비스 시에는 API로 좌표를 가져오지만, 여기서는 샘플 지도를 띄웁니다.
                    sample_map = pd.DataFrame({'lat': [37.5665], 'lon': [126.9780]}) # 서울 시청 기준
                    st.map(sample_map)

                st.session_state.messages.append({"role": "assistant", "content": full_res})
                c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", ("model", full_res, now_str))
                conn.commit()
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")