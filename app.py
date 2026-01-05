import streamlit as st
import google.generativeai as genai
import sqlite3
import json
from datetime import datetime, timedelta, timezone

# -----------------------------
# [설정] 본인 키로 교체
# -----------------------------
# GEMINI_API_KEY = ""

# -----------------------------
# 페이지 설정
# -----------------------------
st.set_page_config(page_title="영구 기억 AI 비서", page_icon="🧠", layout="centered")

# -----------------------------
# 시간 및 DB 설정 (대화 저장용 테이블 추가)
# -----------------------------
KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST)

def init_db():
    conn = sqlite3.connect("smart_bot.db", check_same_thread=False)
    c = conn.cursor()
    # 1. 리마인더 테이블
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    # 2. 대화 기록 테이블 (role: user/model, content: 메시지 내용)
    c.execute("CREATE TABLE IF NOT EXISTS chat_history (role TEXT, content TEXT, timestamp DATETIME)")
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
        return f"✅ 리마인더가 DB에 영구 저장되었습니다: {time_str}에 '{content}' 알림."
    except Exception as e:
        return f"❌ 등록 실패: {str(e)}"

# -----------------------------
# DB에서 대화 기록 불러오기/저장하기 함수
# -----------------------------
def load_chat_history_from_db():
    """DB에서 최근 대화 10개를 가져와 Gemini 형식으로 변환합니다."""
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 10")
    rows = c.fetchall()[::-1] # 오래된 순으로 정렬
    history = []
    for role, content in rows:
        history.append({"role": role, "parts": [content]})
    return history

def save_message_to_db(role, content):
    """대화 내용을 DB에 한 줄 저장합니다."""
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", 
              (role, content, datetime.now()))
    conn.commit()

# -----------------------------
# Gemini 설정
# -----------------------------
genai.configure(api_key="")
model = genai.GenerativeModel(
    model_name='gemini-2.0-flash',
    tools=[get_current_time, register_reminder],
    system_instruction="당신은 대화 내용을 모두 기억하는 유능한 비서입니다. 이전 대화 맥락을 참고하여 답변하세요."
)

# -----------------------------
# 세션 상태 초기화 (DB 데이터 기반)
# -----------------------------
if "messages" not in st.session_state:
    # 처음 접속 시 DB에서 대화 기록을 로드하여 화면에 표시할 준비
    db_history = load_chat_history_from_db()
    st.session_state.messages = []
    for h in db_history:
        role = "assistant" if h["role"] == "model" else "user"
        st.session_state.messages.append({"role": role, "content": h["parts"][0]})
    
    # Gemini 채팅 세션 시작 (DB 기록 주입)
    st.session_state.chat_session = model.start_chat(
        history=db_history, 
        enable_automatic_function_calling=True
    )

# -----------------------------
# UI 렌더링
# -----------------------------
st.title("🧠 영구 기억 AI 비서")
st.caption("이전 대화 내용을 DB에 저장하여 언제든 기억합니다.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("메시지를 입력하세요..."):
    # 1. 유저 메시지 표시 및 DB 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message_to_db("user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. AI 응답 생성 및 DB 저장
    with st.chat_message("assistant"):
        response = st.session_state.chat_session.send_message(prompt)
        full_response = response.text
        st.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        save_message_to_db("model", full_response) # Gemini는 assistant를 'model'로 저장함

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 관리")
    if st.button("전체 기록 삭제 (DB 초기화)"):
        c = conn.cursor()
        c.execute("DELETE FROM chat_history")
        c.execute("DELETE FROM reminders")
        conn.commit()
        st.session_state.messages = []
        st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
        st.success("모든 기억이 삭제되었습니다.")
        st.rerun()