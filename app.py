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

st.set_page_config(page_title="AI 비서", page_icon="🚀", layout="wide")

# --- 1. 시간 및 데이터베이스 설정 ---
KST = timezone(timedelta(hours=9))

def init_db():
    conn = sqlite3.connect("super_bot.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    conn.commit()
    return conn

conn = init_db()

# --- 2. 유틸리티 함수 (좌표 및 지도 링크) ---
def transform_coords(x, y):
    """네이버 KATECH 좌표를 위도/경도로 대략적 변환"""
    try:
        lat = float(y) / 10000000
        lon = float(x) / 10000000
        return lat, lon
    except:
        return 37.5612, 127.0385

def make_naver_map_link(title, address):
    """네이버 지도 검색 결과로 바로 연결되는 URL 생성"""
    search_query = f"{title} {address}"
    return f"https://map.naver.com/v5/search/{search_query.replace(' ', '%20')}"

# --- 3. AI 도구(Tools) 정의 ---
def get_current_time():
    """현재 한국의 날짜와 시간을 확인합니다."""
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def get_weather(city_name: str):
    """특정 도시의 실시간 날씨 정보를 가져옵니다."""
    if not WEATHER_API_KEY: return "날씨 API 키가 설정되지 않았습니다."
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"📍 {city_name}: {res['weather'][0]['description']}, 온도 {res['main']['temp']}°C"
        return f"'{city_name}' 날씨를 찾을 수 없습니다."
    except: return "날씨 조회 중 오류 발생."

def search_naver(query: str):
    """네이버 검색을 통해 장소 정보와 지도 좌표를 가져옵니다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return "네이버 API 키가 없습니다.", []
    
    clean_query = query.replace("맛집", "").replace("추천", "").strip()
    url = f"https://openapi.naver.com/v1/search/local.json?query={clean_query}&display=5&sort=comment"
    
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        
        if not items:
            return f"'{clean_query}'에 대한 검색 결과가 없습니다.", []
        
        results_text = []
        locations = []
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            address = item['address']
            map_link = make_naver_map_link(title, address)
            results_text.append(f"✅ **{title}**\n📍 {address}\n🔗 [네이버 지도로 보기]({map_link})")
            
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon})
            
        return "\n\n".join(results_text), locations
    except:
        return "네이버 검색 중 오류가 발생했습니다.", []

def search_youtube(query: str):
    """유튜브 검색 링크를 제공합니다."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return f"📺 유튜브 검색 결과: {url}"

def register_reminder(time_str: str, content: str):
    """리마인더를 저장합니다. 형식: 'YYYY-MM-DD HH:MM'"""
    c = conn.cursor()
    c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
    conn.commit()
    return f"✅ {time_str}에 '{content}' 등록 완료!"

# --- 4. Gemini 1.5 Flash 설정 ---
genai.configure(api_key=GEMINI_API_KEY)

# 툴 리스트 통합
my_tools = [get_current_time, get_weather, search_naver, search_youtube, register_reminder]

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=my_tools,
    system_instruction="""당신은 만능 AI 비서입니다.
    - 장소/맛집 질문: 'search_naver'를 사용해 정보를 찾고 지도 링크를 안내하세요.
    - 날씨/시간/리마인더/유튜브: 관련 도구를 즉시 호출하세요.
    - 사진 분석: 업로드된 이미지를 보고 상세히 설명하며 필요시 관련 정보를 검색하세요."""
)

# --- 5. UI 및 대화 로직 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)

st.title("🚀 AI 비서")

with st.sidebar:
    st.header("⏰ 리마인더")
    reminders = conn.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC").fetchall()
    for dt, msg in reminders:
        st.write(f"🔔 **{dt}**\n{msg}")

uploaded_file = st.file_uploader("🖼️ 사진 분석", type=["jpg", "png", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, use_container_width=True)

# 채팅 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "map" in msg and msg["map"] is not None:
            st.map(msg["map"])

# 입력 처리
if prompt := st.chat_input("질문을 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("생각 중..."):
            try:
                # 1. 네이버 지도 데이터 수동 확인 (지도 표시용)
                info_text, locations = "", []
                if any(k in prompt for k in ["맛집", "위치", "어디", "장소"]):
                    info_text, locations = search_naver(prompt)

                # 2. Gemini 응답 생성
                if uploaded_file:
                    img = Image.open(uploaded_file)
                    response = st.session_state.chat_session.send_message([prompt, img])
                else:
                    response = st.session_state.chat_session.send_message(prompt)
                
                # 3. 결과 출력 및 지도 표시
                st.markdown(response.text)
                map_df = pd.DataFrame(locations) if locations else None
                if map_df is not None:
                    st.map(map_df)
                
                st.session_state.messages.append({"role": "assistant", "content": response.text, "map": map_df})
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")