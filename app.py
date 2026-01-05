import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image

# --- 0. 설정 및 보안 (Secrets) ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
NAVER_CLIENT_ID = st.secrets.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = st.secrets.get("NAVER_CLIENT_SECRET", "")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")

st.set_page_config(page_title="AI 비서", page_icon="🚀", layout="wide")

# --- 1. 유틸리티 함수 (좌표 변환 포함) ---
KST = timezone(timedelta(hours=9))

def init_db():
    conn = sqlite3.connect("super_bot.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    conn.commit()
    return conn

conn = init_db()

def transform_coords(x, y):
    """네이버 KATECH 좌표를 위도/경도로 대략적 변환 (st.map용)"""
    # 네이버 API의 mapx, mapy는 정수형이므로 숫자로 변환 후 스케일링
    try:
        lat = float(y) / 10000000
        lon = float(x) / 10000000
        # 한국 위경도 범위 내로 보정 (정밀 변환은 복잡하므로 API 기반 근사치 사용)
        if 33 < lat < 39 and 124 < lon < 130:
            return lat, lon
        # 보정이 안될 경우 서울 중심점 근처로 반환
        return 37.5612, 127.0385
    except:
        return 37.5612, 127.0385

# --- 2. AI 도구(Tools) 정의 ---

def search_naver(query: str):
    """네이버 장소 검색 후 결과 텍스트와 지도 좌표를 반환합니다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return "네이버 API 키를 확인해주세요.", []
    
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
            return f"'{clean_query}' 검색 결과가 없습니다.", []
        
        results = []
        locations = []
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            address = item['address']
            results.append(f"✅ **{title}**\n📍 {address}")
            
            # 지도용 좌표 저장
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon, 'name': title})
            
        return "\n\n".join(results), locations
    except:
        return "검색 중 오류가 발생했습니다.", []

def get_weather(city_name: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    res = requests.get(url).json()
    return f"📍 {city_name}: {res['weather'][0]['description']}, {res['main']['temp']}°C" if res.get("cod") == 200 else "날씨 정보 없음"

# --- 3. Gemini 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', 
    tools=[get_weather, search_naver], # 유튜브, 리마인더 등은 필요시 추가
    system_instruction="당신은 맛집 추천 비서입니다. 장소를 물어보면 반드시 search_naver를 사용하고, 결과를 요약해 대답하세요."
)

if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "map_data" not in st.session_state:
    st.session_state.map_data = None

# --- 4. UI 구성 ---
st.title("🚀 AI 비서")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("검색할 내용을 입력하세요."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # 1. 네이버 검색 직접 호출 (지도 데이터를 뽑기 위함)
        res_text, locations = search_naver(prompt)
        
        # 2. Gemini에게 검색 결과 전달 및 답변 생성
        response = st.session_state.chat_session.send_message(f"다음 검색 결과를 바탕으로 친절하게 대답해줘: {res_text}")
        st.markdown(response.text)
        
        # 3. 지도 표시
        if locations:
            df = pd.DataFrame(locations)
            st.map(df)
            st.session_state.map_data = df
        
        st.session_state.messages.append({"role": "assistant", "content": response.text})