import streamlit as st
import requests
import base64
import json
import os
import hashlib
import uuid
import io
import time
from datetime import datetime
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# ================= CONFIG ================= #

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
REASONING_MODEL = "openai/gpt-oss-120b:free"
USER_DB = "users.json"
EXPORT_DIR = "exports"

# ================= SESSION ================= #

def init_session():
    defaults = {
        "logged_in": False,
        "username": None,
        "menu": "Home",
        "chat_history": [],
        "detection_result": None,
        "task_queue": [],
        "reports": [],
        "cost_result": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ================= AUTH ================= #

def init_user_db():
    if not os.path.exists(USER_DB):
        with open(USER_DB, "w") as f:
            json.dump({}, f)

def load_users():
    with open(USER_DB, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USER_DB, "w") as f:
        json.dump(users, f, indent=4)

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def auth_page():
    st.title("🌾 Farm AI Authentication")
    mode = st.radio("Mode", ["Login", "Sign Up"], horizontal=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    users = load_users()

    if mode == "Sign Up":
        if st.button("Create Account"):
            if not username or not password:
                st.error("All fields required")
                return
            if username in users:
                st.error("Username exists")
                return
            users[username] = {
                "password": hash_password(password),
                "id": str(uuid.uuid4())
            }
            save_users(users)
            st.success("Account created. Login now.")
            st.rerun()

    else:
        if st.button("Login"):
            if username not in users:
                st.error("User not found")
                return
            if hash_password(password) == users[username]["password"]:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Wrong password")

# ================= API ================= #

def call_openrouter(messages, model):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": model, "messages": messages}
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload)

    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    data = r.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    return "Unexpected response"

# ================= VISION ================= #

def analyze_image(img_bytes, location):
    img_base64 = base64.b64encode(img_bytes).decode()

    prompt = f"""
Analyze this crop image.
Location: {location}

Return ONLY valid JSON:
{{
"crop_name":"",
"disease_name":"",
"description":"",
"solution":"",
"fertilizers":"",
"soil_insights":"",
"water_forecast":"",
"risk_score":""
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                }
            ]
        }]
    }

    r = requests.post(OPENROUTER_URL, headers=headers, json=payload)

    if r.status_code != 200:
        return {"error": r.text}

    output = r.json()["choices"][0]["message"]["content"]

    try:
        if "```" in output:
            output = output.split("```")[1]
        return json.loads(output)
    except:
        return {"error": "Parsing failed"}

# ================= COST ENGINE ================= #

def cost_estimation(location, crop, acres, investment):
    prompt = f"""
Location: {location}
Crop: {crop}
Acres: {acres}
Investment: {investment}

Provide JSON:
{{
"market_price":"",
"best_months":"",
"total_cost":"",
"expected_revenue":"",
"profit_or_loss":"",
"recommendation":""
}}
"""
    result = call_openrouter(
        [
            {"role": "system", "content": "You are an agricultural economist."},
            {"role": "user", "content": prompt}
        ],
        REASONING_MODEL
    )
    return result

# ================= TASK AGENT ================= #

def queue_task(title, prompt):
    st.session_state.task_queue.append({"title": title, "prompt": prompt})

def run_tasks():
    while st.session_state.task_queue:
        task = st.session_state.task_queue.pop(0)
        result = call_openrouter(
            [
                {"role": "system", "content": "Generate structured operational farm report."},
                {"role": "user", "content": task["prompt"]}
            ],
            REASONING_MODEL
        )
        st.session_state.reports.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": task["title"],
            "content": result
        })

# ================= EXPORT ================= #

def export_chat():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    lines = []
    for m in st.session_state.chat_history:
        lines.append(f"[{m['time']}] {m['role']}: {m['text']}")

    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.05, 0.95, "\n".join(lines), va="top", fontsize=9)
        plt.axis("off")
        pdf.savefig(fig)
        plt.close(fig)

    return path

# ================= UI ================= #

def sidebar():
    with st.sidebar:
        st.title("🤖 Farm AI")
        st.session_state.menu = st.radio("Navigation", ["Home", "Chat", "Reports", "Cost"])
        st.write("User:", st.session_state.username)

        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

# ================= PAGES ================= #

def home():
    st.title("🌾 Crop Intelligence")

    location = st.text_input("Farm Location")
    file = st.file_uploader("Upload Leaf Image", type=["jpg","png","jpeg"])

    if file:
        img = Image.open(file)
        st.image(img, use_container_width=True)

        if st.button("Analyze"):
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            result = analyze_image(buffer.getvalue(), location)
            st.session_state.detection_result = result

    if st.session_state.detection_result:
        r = st.session_state.detection_result
        if "error" in r:
            st.error(r["error"])
            return

        st.success(r.get("crop_name","Unknown"))
        st.warning(r.get("disease_name","Healthy"))
        st.info(r.get("description","No description"))
        st.success(r.get("solution","No solution"))
        st.info(r.get("fertilizers","No fertilizer"))
        st.write("Soil:", r.get("soil_insights",""))
        st.write("Water:", r.get("water_forecast",""))
        st.error("Risk:", r.get("risk_score","Unknown"))

def chat():
    st.title("💬 Farm AI Chat")

    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]):
            st.markdown(m["text"])

    user_input = st.chat_input("Ask about farming...")

    if user_input:
        st.session_state.chat_history.append({
            "role":"user",
            "text":user_input,
            "time":datetime.now().strftime("%H:%M:%S")
        })

        with st.chat_message("assistant"):
            response = call_openrouter(
                [
                    {"role":"system","content":"You are an advanced agricultural AI."},
                    {"role":"user","content":user_input}
                ],
                REASONING_MODEL
            )
            st.markdown(response)

        st.session_state.chat_history.append({
            "role":"assistant",
            "text":response,
            "time":datetime.now().strftime("%H:%M:%S")
        })

        st.rerun()

def reports():
    st.title("📊 Agent Reports")

    if st.button("Run Soil Analysis"):
        queue_task("Soil Analysis", "Generate soil health operational report.")
    if st.button("Run Market Forecast"):
        queue_task("Market Forecast", "Generate crop market forecast.")

    if st.button("Execute Tasks"):
        run_tasks()

    for r in st.session_state.reports:
        with st.expander(f"{r['title']} ({r['time']})"):
            st.write(r["content"])

def cost():
    st.title("💰 Cost Estimation")

    loc = st.text_input("Location")
    crop = st.text_input("Crop")
    acres = st.number_input("Acres", 0.0)
    invest = st.number_input("Investment", 0.0)

    if st.button("Estimate"):
        st.session_state.cost_result = cost_estimation(loc, crop, acres, invest)

    if st.session_state.cost_result:
        st.write(st.session_state.cost_result)

# ================= MAIN ================= #

init_user_db()
init_session()

if not st.session_state.logged_in:
    auth_page()
    st.stop()

sidebar()

if st.session_state.menu == "Home":
    home()
elif st.session_state.menu == "Chat":
    chat()
elif st.session_state.menu == "Reports":
    reports()
else:
    cost()
