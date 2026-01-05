import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image
from urllib.parse import quote  # URL 인코딩을 위해 필수

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

def make_naver_map_link(title):
    """
    네이버 지도 검색 링크를 생성합니다.
    주소 대신 '가게명 + 지점명'으로만 검색하여 네이버 지도에서 가장 정확한 결과를 띄웁니다.
    """
    # 네이버 API 결과의 <b> 태그 제거
    clean_title = title.replace('<b>', '').replace('</b>', '').strip()
    # URL에 한글/공백이 들어갈 수 있도록 인코딩
    return f"https://map.naver.com/v5/search/{quote(clean_title)}"

# --- 2. 통합 도구(Tools) 정의 ---
def search_naver(query: str):
    """네이버에서 장소 정보를 검색합니다."""
    if not NAVER_CLIENT_ID: return "네이버 API 설정 필요", []
    
    # 검색 정확도를 위해 sort를 comment(리뷰순)로 설정 가능
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=5&sort=comment"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        if not items: return "검색 결과가 없습니다.", []
        
        info_list = []
        locations = []
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            address = item['address']
            
            # [수정 포인트] 링크 생성 시 '가게명(지점명 포함)'만 사용
            link = make_naver_map_link(title)
            
            info_list.append(f"📍 **{title}** ({item['category']})\n- 주소: {address}\n- [🔗 네이버 지도로 보기]({link})")
            
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon})
            
        return "\n\n".join(info_list), locations
    except: return "검색 오류 발생", []

# --- 3. Gemini 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[search_naver], # 필요한 도구 추가 (날씨 등)
    system_instruction="""당신은 친절한 AI 비서입니다. 
    1. 장소 검색 시 'search_naver' 결과를 바탕으로 대답하세요.
    2. 답변에 '가게명', '카테고리', '주소'를 포함하여 깔끔하게 리스트로 보여주세요.
    3. 링크는 반드시 '[🔗 네이버 지도로 보기](URL)' 형식만 사용하고, URL 주소 자체는 밖으로 노출하지 마세요."""
)

# --- 4. UI 구성 ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🚀 AI 비서")

# 채팅 로그 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "map" in msg and msg["map"] is not None:
            st.map(msg["map"])

if prompt := st.chat_input("왕십리 맛집 알려줘!"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("최적의 장소를 찾는 중..."):
            try:
                # 지도 표시를 위한 데이터 미리 추출
                info_text, locations = "", []
                if any(k in prompt for k in ["어디", "맛집", "장소", "근처"]):
                    info_text, locations = search_naver(prompt)
                
                # Gemini 답변 생성
                response = st.session_state.chat_session.send_message(prompt)
                st.markdown(response.text)
                
                # 지도 표시
                map_df = pd.DataFrame(locations) if locations else None
                if map_df is not None:
                    st.map(map_df)
                
                st.session_state.messages.append({"role": "assistant", "content": response.text, "map": map_df})
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")