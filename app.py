import streamlit as st
import requests
import base64
import json
import os
import hashlib
import uuid
from datetime import datetime
from PIL import Image
import io

# ================= CONFIG ================= #

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
REASONING_MODEL = "openai/gpt-oss-120b:free"
USER_DB = "users.json"

# ================= USER DB ================= #

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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ================= SESSION ================= #

def ensure_session_defaults():
    defaults = {
        "logged_in": False,
        "username": None,
        "chat_history": [],
        "detection_result": None,
        "menu": "Home"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ================= AUTH ================= #

def auth_page():
    st.title("🌾 Farm AI Authentication")

    mode = st.radio("Select Mode", ["Login", "Sign Up"], horizontal=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    users = load_users()

    if mode == "Sign Up":
        if st.button("Create Account"):
            if not username or not password:
                st.error("All fields required.")
                return

            if username in users:
                st.error("Username already exists.")
                return

            users[username] = {
                "password": hash_password(password),
                "id": str(uuid.uuid4())
            }
            save_users(users)
            st.success("Account created. Please login.")
            st.rerun()

    else:
        if st.button("Login"):
            if username not in users:
                st.error("User not found.")
                return

            if hash_password(password) == users[username]["password"]:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Login successful.")
                st.rerun()
            else:
                st.error("Incorrect password.")

# ================= API CALL ================= #

def call_openrouter(messages, model):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return f"Error {response.status_code}: {response.text}"

    data = response.json()

    if "choices" in data:
        return data["choices"][0]["message"]["content"]

    return "Unexpected API response."

# ================= IMAGE ANALYSIS ================= #

def analyze_image(image_bytes, location):
    base64_image = base64.b64encode(image_bytes).decode()

    prompt = f"""
Analyze plant image.
Location: {location}

Return ONLY valid JSON:

{{
"crop_name": "",
"disease_name": "",
"description": "",
"solution": "",
"fertilizers": "",
"soil_insights": "",
"water_forecast": "",
"risk_score": ""
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return {"error": response.text}

    result = response.json()
    output = result["choices"][0]["message"]["content"]

    try:
        if "```" in output:
            output = output.split("```")[1].strip()
        return json.loads(output)
    except:
        return {"error": "Failed to parse model output"}

# ================= SIDEBAR ================= #

def sidebar():
    with st.sidebar:
        st.title("🤖 Farm AI")

        st.session_state.menu = st.radio(
            "Navigation",
            ["Home", "Chat"]
        )

        st.markdown("---")
        st.write("Logged in as:", st.session_state.username)

        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

# ================= HOME ================= #

def home_page():
    st.title("🌾 Agricultural Super AI")

    location = st.text_input("Farm Location")

    uploaded_file = st.file_uploader("Upload Leaf Image", type=["jpg", "jpeg", "png"])

    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, use_container_width=True)

        if st.button("Analyze"):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            result = analyze_image(buffer.getvalue(), location)
            st.session_state.detection_result = result

    if st.session_state.detection_result:
        res = st.session_state.detection_result

        if "error" in res:
            st.error(res["error"])
            return

        st.markdown("## 🌿 Crop Identified")
        st.success(res.get("crop_name", "Unknown"))

        st.markdown("## 🦠 Disease Status")
        st.warning(res.get("disease_name", "Healthy"))

        st.markdown("## 📄 Description")
        st.info(res.get("description", "No description available."))

        st.markdown("## 💊 Solution")
        st.success(res.get("solution", "No solution available."))

        st.markdown("## 🧪 Fertilizers")
        st.info(res.get("fertilizers", "No fertilizer info."))

        st.markdown("## 🌱 Soil Insights")
        st.write(res.get("soil_insights", "No soil data."))

        st.markdown("## 💧 Water Forecast")
        st.write(res.get("water_forecast", "No water forecast."))

        st.markdown("## ⚠ Risk Score")
        st.error(res.get("risk_score", "Unknown"))

# ================= CHAT ================= #

def chat_page():
    st.title("💬 Farm AI Chat")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["text"])

    user_input = st.chat_input("Ask about crops, disease, irrigation...")

    if user_input:
        st.session_state.chat_history.append({
            "role": "user",
            "text": user_input,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        with st.chat_message("assistant"):
            response = call_openrouter(
                [
                    {"role": "system", "content": "You are an advanced agricultural AI."},
                    {"role": "user", "content": user_input}
                ],
                REASONING_MODEL
            )
            st.markdown(response)

        st.session_state.chat_history.append({
            "role": "assistant",
            "text": response,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        st.rerun()

# ================= MAIN ================= #

init_user_db()
ensure_session_defaults()

if not st.session_state.logged_in:
    auth_page()
    st.stop()

sidebar()

if st.session_state.menu == "Home":
    home_page()
else:
    chat_page()
