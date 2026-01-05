import streamlit as st
import google.generativeai as genai
import sqlite3
from datetime import datetime, timedelta, timezone

# [설정] 본인 키로 교체
GEMINI_API_KEY = ""

st.set_page_config(page_title="만능 지식인 AI", page_icon="🌟", layout="centered")

# --- DB 설정 (기존과 동일) ---
def init_db():
    conn = sqlite3.connect("smart_bot.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS reminders (datetime TEXT, message TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS chat_history (role TEXT, content TEXT, timestamp DATETIME)")
    conn.commit()
    return conn

conn = init_db()

# --- 도구 정의 (기존 유지) ---
def get_current_time():
    """현재 날짜와 시간을 확인합니다."""
    now = datetime.now(timezone(timedelta(hours=9)))
    return now.strftime('%Y년 %m월 %d일 %H시 %M분 %S초 입니다.')

def register_reminder(time_str: str, content: str):
    """리마인더를 등록합니다."""
    c = conn.cursor()
    c.execute("INSERT INTO reminders (datetime, message) VALUES (?, ?)", (time_str, content))
    conn.commit()
    return f"✅ 기록 완료: {time_str}에 '{content}' 알림을 저장했습니다."

# --- Gemini 설정 (업그레이드 포인트!) ---
genai.configure(api_key="")

# 1. AI의 성격과 능력을 부여합니다.
SYSTEM_PROMPT = """
당신은 세상의 모든 지식을 알고 있는 '만능 AI 지식인'입니다. 
사용자의 질문에 대해 다음과 같은 원칙으로 답하세요:
1. 답변은 항상 친절하고 풍부하게 작성하세요.
2. 모르는 내용이 있다면 추측하지 말고 솔직하게 말하되, 도움이 될 만한 대안을 제시하세요.
3. 사용자가 과거에 했던 말을 DB에서 기억하고 있으니, 맥락을 적극 활용하세요.
4. 필요하다면 도구(시간 확인, 리마인더)를 사용해 실질적인 도움을 주세요.
5. 유머 감각을 발휘하여 친구처럼 대화할 수도 있습니다.
"""

# 2. 창의성 설정을 추가하여 답변을 더 풍부하게 만듭니다.
generation_config = {
    "temperature": 0.9,  # 높을수록 창의적이고 다양한 답변이 나옵니다.
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[get_current_time, register_reminder],
    system_instruction=SYSTEM_PROMPT,
    generation_config=generation_config # 창의성 설정 적용
)

# --- 대화 로직 (기존 영구 기억 로직 유지) ---
def load_chat_history_from_db():
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 15") # 기억력 강화 (15개)
    rows = c.fetchall()[::-1]
    return [{"role": role, "parts": [content]} for role, content in rows]

def save_message_to_db(role, content):
    c = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)", (role, content, now_str))
    conn.commit()

if "messages" not in st.session_state:
    db_history = load_chat_history_from_db()
    st.session_state.messages = [{"role": ("assistant" if h["role"] == "model" else "user"), "content": h["parts"][0]} for h in db_history]
    st.session_state.chat_session = model.start_chat(history=db_history, enable_automatic_function_calling=True)

# --- UI 레이아웃 ---
st.title("🌟 만능 지식인 AI")
st.write("무엇이든 물어보세요! 당신의 모든 말을 기억하고 대답해 드립니다.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("질문, 고민상담, 리마인더 등록 등 무엇이든 말씀하세요!"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message_to_db("user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response = st.session_state.chat_session.send_message(prompt)
        full_response = response.text
        st.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        save_message_to_db("model", full_response)

# 사이드바 (기존 유지)
with st.sidebar:
    st.header("⏰ 예정된 리마인더")
    # ... 리마인더 표시 로직 ...