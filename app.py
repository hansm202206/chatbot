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

# --- 1. 유틸리티 함수 ---
KST = timezone(timedelta(hours=9))

def transform_coords(x, y):
    try:
        return float(y) / 10000000, float(x) / 10000000
    except:
        return 37.5612, 127.0385

def make_naver_map_link(title, address):
    search_query = f"{title} {address}"
    return f"https://map.naver.com/v5/search/{search_query.replace(' ', '%20')}"

# --- 2. 통합 검색 함수 (하드코딩 필터 제거) ---
def search_naver(query: str):
    """사용자 질문에 따라 네이버에서 장소 정보를 가져옵니다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return "네이버 API 설정을 확인해주세요.", []
    
    # 검색어에서 불필요한 조사만 제거하여 네이버에 전달
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=8&sort=random"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        
        if not items:
            return f"'{query}'에 대한 검색 결과가 없습니다.", []
        
        raw_data_for_ai = [] # AI가 판단할 수 있도록 날것의 데이터를 담음
        locations = []
        
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            address = item['address']
            category = item['category']
            link = make_naver_map_link(title, address)
            
            # AI에게 전달할 정보 구성
            raw_data_for_ai.append(f"명칭: {title}, 카테고리: {category}, 주소: {address}, 링크: {link}")
            
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon, 'name': title})
            
        return "\n".join(raw_data_for_ai), locations
    except:
        return "검색 중 오류가 발생했습니다.", []

# --- 3. 기타 기능 (기존 기능 유지) ---
def get_current_time():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def get_weather(city_name: str):
    if not WEATHER_API_KEY: return "날씨 API 키 없음"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    res = requests.get(url).json()
    return f"📍 {city_name}: {res['main']['temp']}°C" if res.get("cod") == 200 else "정보 없음"

# --- 4. Gemini 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[get_current_time, get_weather, search_naver],
    system_instruction="""당신은 사용자의 의도를 완벽히 파악하는 비서입니다.
    1. 사용자가 장소를 물어보면 'search_naver'를 호출하세요.
    2. 검색 결과(raw_data)를 받으면, 사용자의 질문 의도에 맞는 장소만 골라서 답변하세요. 
       (예: 맛집을 물었는데 미용실이 결과에 있으면 미용실은 제외하고 답변하세요.)
    3. 만약 미용실을 물었다면 당연히 미용실 정보를 친절하게 안내하세요.
    4. 각 장소마다 제공된 네이버 지도 링크를 반드시 포함하세요."""
)

# --- 5. UI 및 로직 ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🤖 AI 비서")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "map" in msg and msg["map"] is not None:
            st.map(msg["map"])

if prompt := st.chat_input("무엇이든 물어보세요 (예: 왕십리 곱창, 근처 미용실, 서울 날씨)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("정보 분석 중..."):
            try:
                # Gemini가 도구(search_naver 등)를 알아서 판단하여 실행
                response = st.session_state.chat_session.send_message(prompt)
                
                # 지도 좌표 추출을 위해 검색 결과가 있는지 세션에서 확인 (로직 간소화 가능)
                # 여기서는 단순화를 위해 결과 텍스트만 먼저 출력
                st.markdown(response.text)
                
                # 세션 저장
                st.session_state.messages.append({"role": "assistant", "content": response.text, "map": None})
            except Exception as e:
                st.error(f"오류: {e}")