import streamlit as st
import google.generativeai as genai
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image
from urllib.parse import quote

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
    """가게명+지점명으로 깔끔한 검색 링크 생성 (URL 인코딩 적용)"""
    clean_title = title.replace('<b>', '').replace('</b>', '').strip()
    return f"https://map.naver.com/v5/search/{quote(clean_title)}"

# --- 2. 지능형 검색 함수 (하드코딩 필터 없음) ---
def search_naver(query: str):
    """네이버에서 장소 정보를 가져옵니다. 필터링은 AI가 직접 수행합니다."""
    if not NAVER_CLIENT_ID: return "네이버 API 설정 필요", []
    
    # AI가 판단할 수 있도록 넉넉히(10개) 가져옵니다.
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=10&sort=random"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    
    try:
        res = requests.get(url, headers=headers).json()
        items = res.get('items', [])
        if not items: return "검색 결과가 없습니다.", []
        
        raw_data_for_ai = []
        locations = []
        for item in items:
            title = item['title'].replace('<b>', '').replace('</b>', '')
            address = item['address']
            category = item['category']
            link = make_naver_map_link(title) # 개선된 링크 함수 적용
            
            # AI에게 전달할 원시 데이터
            raw_data_for_ai.append(f"명칭: {title}, 카테고리: {category}, 주소: {address}, 링크: {link}")
            
            lat, lon = transform_coords(item['mapx'], item['mapy'])
            locations.append({'lat': lat, 'lon': lon, 'name': title})
            
        return "\n".join(raw_data_for_ai), locations
    except: return "검색 중 오류 발생", []

# --- 3. 기타 도구 정의 (날씨, 시간, 유튜브) ---
def get_current_time():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

def get_weather(city_name: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    res = requests.get(url).json()
    return f"📍 {city_name}: {res['main']['temp']}°C, {res['weather'][0]['description']}" if res.get("cod")==200 else "날씨 정보 없음"

def search_youtube(query: str):
    return f"📺 유튜브 검색 결과: https://www.youtube.com/results?search_query={quote(query)}"

# --- 4. Gemini 설정 (지능형 판단 가이드) ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[get_current_time, get_weather, search_naver, search_youtube],
    system_instruction="""당신은 사용자의 의도를 정확히 파악하는 지능형 비서입니다.
    1. 장소 검색 시 'search_naver'를 호출하고, 결과를 받으면 사용자의 질문에 적합한 장소만 선별하세요.
       (예: 맛집 질문에 미용실이 섞여있으면 미용실은 제외하고 답변)
    2. 답변 시 각 장소의 '주소'를 포함하고, 링크는 반드시 '[🔗 네이버 지도로 보기](URL)' 형식으로만 작성하세요.
    3. URL 주소를 텍스트로 노출하지 말고 마크다운 링크 안에 숨기세요.
    4. 친절하고 가독성 좋게 리스트 형태로 답변하세요."""
)

# --- 5. UI 로직 ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🤖 AI 비서")

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

if prompt := st.chat_input("검색할 내용을 입력하세요."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("의도 파악 및 정보 분석 중..."):
            try:
                # 지도 표시를 위한 데이터 추출 (맛집/장소 질문일 경우)
                info_text, locations = "", []
                if any(k in prompt for k in ["어디", "맛집", "장소", "근처", "찾아", "추천"]):
                    info_text, locations = search_naver(prompt)
                
                input_content = [prompt, Image.open(uploaded_file)] if uploaded_file else prompt
                response = st.session_state.chat_session.send_message(input_content)
                
                st.markdown(response.text)
                map_df = pd.DataFrame(locations) if locations else None
                if map_df is not None: st.map(map_df)
                
                st.session_state.messages.append({"role": "assistant", "content": response.text, "map": map_df})
            except Exception as e:
                st.error(f"오류 발생: {e}")