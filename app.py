import streamlit as st
import google.generativeai as genai
import sqlite3
from datetime import datetime, timedelta, timezone

# -----------------------------
# [설정] 본인 키로 교체
# -----------------------------
GEMINI_API_KEY = "AIzaSyDd4otbfFEDQArGV82Z2VJhtEOSiQQkaiU"

# -----------------------------
# 페이지 설정 (앱 느낌 내기)
# -----------------------------
st.set_page_config(page_title="나만의 AI 비서", page_icon="🤖", layout="centered")

# 모바일에서 앱처럼 보이게 하는 커스텀 CSS
st.markdown("""
    <style>
    .stChatMessage { border-radius: 15px; margin-bottom: 10px; }
    .stChatInputContainer { padding-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# -----------------------------
# 시간 및 DB 설정
# -----------------------------
KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST)

def init_db():
    conn = sqlite3.connect("web_bot_data.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    conn.commit()
    return conn

conn = init_db()

# -----------------------------
# AI 도구(Tools) 정의
# -----------------------------
def get_current_time():
    """현재 날짜와 시간을 확인합니다."""
    now = now_kst()
    weekday = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][now.weekday()]
    return f"현재 시각은 {now.year}년 {now.month}월 {now.day}일 {weekday} {now.strftime('%H:%M:%S')} 입니다."

def register_reminder(time_str: str, content: str):
    """리마인더를 등록합니다. time_str 형식: 'YYYY-MM-DD HH:MM'"""
    try:
        c = conn.cursor()
        c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
        conn.commit()
        return f"✅ 확인되었습니다. {time_str}에 '{content}'라고 알려드릴게요."
    except Exception as e:
        return f"❌ 등록 실패: {str(e)}"

# -----------------------------
# Gemini 설정
# -----------------------------
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.0-flash', # 혹은 gemini-2.0-flash-exp
    tools=[get_current_time, register_reminder],
    system_instruction="당신은 유능한 비서입니다. 시간 확인과 리마인더 등록 도구를 적극 활용하세요."
)

# -----------------------------
# 대화 기록 관리 (State)
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [] # 화면 표시용
if "chat_session" not in st.session_state:
    # Gemini 대화 세션 유지
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)

# -----------------------------
# 메인 화면 UI
# -----------------------------
st.title("🤖 스마트 AI 비서")
st.caption("시간 확인부터 리마인더 등록까지 도와드려요.")

# 저장된 대화 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 사용자 입력
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 1. 사용자 메시지 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. AI 응답 생성
    with st.chat_message("assistant"):
        try:
            response = st.session_state.chat_session.send_message(prompt)
            full_response = response.text
            st.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")

# 사이드바: 등록된 리마인더 확인
with st.sidebar:
    st.header("⏰ 예정된 리마인더")
    c = conn.cursor()
    c.execute("SELECT datetime, message FROM reminders ORDER BY datetime ASC")
    rows = c.fetchall()
    if rows:
        for dt, msg in rows:
            st.write(f"**{dt}**\n{msg}")
            st.divider()
    else:
        st.write("등록된 리마인더가 없습니다.")
    
    if st.button("대화 기록 초기화"):
        st.session_state.messages = []
        st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
        st.rerun()