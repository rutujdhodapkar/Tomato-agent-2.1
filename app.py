import hashlib
import uuid
import json
import os
import streamlit as st

USER_DB = "users.json"

# ================= USER DATABASE ================= #

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


# ================= SECURITY ================= #

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ================= SESSION DEFAULTS ================= #

def ensure_session_defaults():
    defaults = {
        "logged_in": False,
        "username": None,
        "auth_mode": "Login",  # Login or Signup
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ================= AUTH UI ================= #

def auth_page():
    st.title("🌾 Farm AI Authentication")

    st.session_state.auth_mode = st.radio(
        "Select Mode",
        ["Login", "Sign Up"],
        horizontal=True
    )

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    users = load_users()

    if st.session_state.auth_mode == "Sign Up":
        if st.button("Create Account"):
            if not username or not password:
                st.error("All fields required.")
                return

            if username in users:
                st.error("Username already exists.")
                return

            users[username] = {
                "password": hash_password(password),
                "user_id": str(uuid.uuid4())
            }

            save_users(users)

            st.success("Account created successfully. Please login.")
            st.session_state.auth_mode = "Login"
            st.rerun()

    else:  # Login mode
        if st.button("Login"):
            if username not in users:
                st.error("User not found.")
                return

            stored_hash = users[username]["password"]
            if hash_password(password) == stored_hash:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Login successful.")
                st.rerun()
            else:
                st.error("Incorrect password.")
        # 🔥 Ensure JSON response
        if "application/json" not in response.headers.get("Content-Type", ""):
            return f"API returned non-JSON response:\n{response.text[:500]}"

        data = response.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        if "error" in data:
            return f"API Error: {data['error'].get('message')}"
        return f"Unexpected format: {data}"
    except requests.exceptions.RequestException as e:
        return f"Network Error: {str(e)}"


def run_reasoning_model(image_bytes, species_info):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = f"""
    Analyze this plant image and the provided metadata. 
    Metadata: {json.dumps(species_info)}

    Identify:
    1. The specific Crop/Plant name.
    2. The most likely Disease or Health Issue (if any). If healthy, state 'Healthy'.
    3. Local soil health trend (nutrients, pH, moisture) based on common conditions for the location and crop.
    4. Water forecast & irrigation suggestions for the next 7 days.
    5. Overall risk score (Low / Medium / High).

    Return ONLY valid JSON in this structure:
    {{
        "crop_name": "Name of the crop",
        "disease_name": "Name of the disease or 'Healthy'",
        "description": "Brief description of the crop and disease condition",
        "solution": "Step-by-step solution to fix the issue or care instructions if healthy",
        "fertilizers": "Recommended fertilizers or nutrients for this specific condition and crop",
        "soil_insights": "Detailed soil health insights (nutrients, pH, moisture)",
        "water_forecast": "Water forecast and irrigation plan",
        "risk_score": "Low/Medium/High"
    }}
    """

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
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

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    
    if response.status_code != 200:
        return {"error": f"HTTP Error {response.status_code}: {response.text}"}

    if "application/json" not in response.headers.get("Content-Type", ""):
        return {"error": "API returned non-JSON response", "raw": response.text[:500]}

    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError:
         return {"error": "Failed to decode JSON", "raw": response.text[:500]}

    if "choices" not in result:
        err_msg = "Unknown error"
        if "error" in result:
            err_msg = result["error"].get("message", "Unknown error")
        return {"error": f"API Error: {err_msg}", "raw_response": result}

    try:
        output_text = result["choices"][0]["message"]["content"]
        # Remove markdown code blocks if present
        if "```json" in output_text:
            output_text = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            output_text = output_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(output_text)
    except Exception as e:
        return {"error": f"Reasoning model failed to parse output: {str(e)}", "raw_response": result}


def ensure_session_defaults():
    defaults = {
        "language": "English",
        "theme": "Light",
        "logged_in": False,
        "username": "",
        "photo_url": "https://api.dicebear.com/8.x/adventurer/png?seed=Farmer",
        "agent_status": "Idle",
        "task_queue": [],
        "reports": [],
        "chat_history": [],
        "detection_result": None,
        "menu_choice": "Home",
        "location": "",
        "cost_estimation": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_local_font(language):
    font_family = FONT_MAP.get(language, FONT_MAP["English"])
    st.markdown(
        f"""
        <style>
            html, body, [class*="css"], .stApp {{
                font-family: {font_family};
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def queue_task(task_name, prompt, model=REASONING_MODEL):
    st.session_state.task_queue.append({"task": task_name, "prompt": prompt, "model": model})


def run_all_background_tasks():
    while st.session_state.task_queue:
        task = st.session_state.task_queue.pop(0)
        st.session_state.agent_status = f"Running: {task['task']}"
        
        report = call_openrouter(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an agricultural super-agent. "
                        "Give structured operational report with metrics, risk score, timeline, ROI impact."
                    ),
                },
                {"role": "user", "content": task["prompt"]},
            ],
            task["model"],
        )

        st.session_state.reports.insert(
            0,
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": task["task"],
                "content": report,
            },
        )

    st.session_state.agent_status = "All tasks completed"


def export_chat_to_pdf():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    lines = ["AI Agent Chat Export", ""]
    for msg in st.session_state.chat_history:
        lines.append(f"[{msg['time']}] {msg['role'].upper()}: {msg['text']}")

    page_lines = 35
    with PdfPages(path) as pdf:
        for i in range(0, max(len(lines), 1), page_lines):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.patch.set_facecolor('white')
            text_chunk = "\n".join(lines[i:i + page_lines]) or "No chat messages to export."
            fig.text(0.05, 0.95, text_chunk, va='top', fontsize=9, family='sans-serif', wrap=True)
            plt.axis('off')
            pdf.savefig(fig)
            plt.close(fig)

    return path


def login_block(lang_text):
    if not os.path.exists(USER_DB):
        with open(USER_DB, "w", encoding="utf-8") as file:
            json.dump({}, file)

    with open(USER_DB, "r", encoding="utf-8") as file:
        users = json.load(file)

    if st.session_state.logged_in:
        return

    st.title(lang_text["login"])
    username = st.text_input(lang_text["username"])
    password = st.text_input(lang_text["password"], type="password")

    if st.button("Continue"):
        if username in users and users[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful")
            st.rerun()
        else:
            users[username] = password
            with open(USER_DB, "w", encoding="utf-8") as file:
                json.dump(users, file)
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Account created")
            st.rerun()
    st.stop()


def sidebar_controls(lang_text):
    with st.sidebar:
        st.title("🤖 Agent Control Panel")

        # Language selection with Apply button
        current_lang_idx = list(TRANSLATIONS.keys()).index(st.session_state.language)
        new_lang = st.selectbox("Select Language", list(TRANSLATIONS.keys()), index=current_lang_idx)
        
        if st.button("Apply Language"):
            st.session_state.language = new_lang
            st.rerun()

        st.session_state.theme = st.selectbox("Theme", ["Light", "Dark"])

        st.markdown("---")
        st.subheader("📊 Cost Estimation")

        # Inputs
        est_location = st.text_input("Location (city/region)")
        est_crop = st.text_input("Crop name")
        est_acres = st.number_input("Total acres", min_value=0.0, step=0.1)
        est_invested = st.number_input("Total invested (₹ or $)", min_value=0.0, step=100.0)

        if st.button("Estimate Cost & Profit"):
            if not (est_location and est_crop and est_acres > 0):
                st.error("Please fill all fields correctly.")
            else:
                # build prompt
                cost_prompt = f"""
                Location: {est_location}
                Crop: {est_crop}
                Acres: {est_acres}
                Investment: {est_invested}

                Provide a cost, revenue & profit analysis including:
                1) Current local market price per unit (use web inference)
                2) Expected monthly prices and best months to sell
                3) Estimate total cost, revenue, profit/loss
                4) Travel costs if selling outside local mandi/market
                5) Suggested sale timing and risk factors

                Format as JSON:
                {{
                  "market_price": "...",
                  "price_trend": "...",
                  "best_months": [...],
                  "total_cost": "...",
                  "expected_revenue": "...",
                  "profit_or_loss": "...",
                  "travel_costs": "...",
                  "recommendation": "..."
                }}
                """
                estimation = call_openrouter(
                    [
                        {"role": "system", "content": "You are an agricultural economic analyst."},
                        {"role": "user", "content": cost_prompt},
                    ],
                    REASONING_MODEL
                )
                st.session_state.cost_estimation = estimation

        st.markdown("---")
        st.subheader("Quick Agent Actions")

        selected_action = st.selectbox("Select analysis", list(ACTION_MAP.keys()))
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Run analysis"):
                queue_task(selected_action, ACTION_MAP[selected_action])
                st.success(f"Queued: {selected_action}")
        
        with col2:
            if st.button("Do all analysis"):
                for action, prompt in ACTION_MAP.items():
                    queue_task(action, prompt)
                st.success("All analyses queued!")

        if st.button("Run all core layers"):
            for layer_task in [
                "Vision Layer", "Climate Layer", "Soil Layer", "Water Layer", "Market Layer", "Execution Layer"
            ]:
                queue_task(layer_task, f"Generate operational report for {layer_task} with metrics and actions.")
            st.success("All layer analyses queued.")

        st.markdown("---")
        st.subheader("Chat Export")
        if st.button("Export chat as PDF"):
            pdf_path = export_chat_to_pdf()
            st.success(f"Saved: {pdf_path}")

        st.markdown("---")
        st.subheader("User")
        st.image(st.session_state.photo_url, width=70)
        st.write(st.session_state.username)

        with st.expander("Profile menu"):
            if st.button("Settings"):
                st.info("Theme / Logout / More available below")
            st.write("• Theme")
            st.write("• Logout")
            st.write("• More")
            if st.button("Logout"):
                st.session_state.logged_in = False
                st.rerun()


def home_page(lang_text):
    st.title("🌾 Agricultural Super AI Agent")
    st.session_state.location = st.text_input("Farm location", value=st.session_state.location)
    location = st.session_state.location # Local reference
    uploaded_image = st.file_uploader(lang_text["upload"], type=["jpg", "jpeg", "png"])

    if uploaded_image:
        image = Image.open(uploaded_image)
        st.image(image, caption="Uploaded Leaf", use_container_width=True)
        
        if st.button(lang_text["analyze"]):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            img_bytes = buffer.getvalue()
            
            # Sequential Status Messages
            status_container = st.empty()
            with status_container.container():
                st.markdown("### 🔁 Running full farm intelligence pipeline...")
                st.write("• Getting location info…")
                time.sleep(0.5)
                st.write("• Fetching local soil reports…")
                time.sleep(0.5)
                st.write("• Fetching local water & weather insights…")
                time.sleep(0.5)
                st.write("• Analyzing image…")
                time.sleep(0.5)
                st.write("• Thinking…")
                time.sleep(1)

            species_info = {"location": location}
            result = run_reasoning_model(img_bytes, species_info)
            status_container.empty()
            st.session_state.detection_result = result
            
            if "error" not in result:
                st.success("Analysis Complete!")
            else:
                st.error(result["error"])

    if st.session_state.detection_result and "error" not in st.session_state.detection_result:
        res = st.session_state.detection_result
        
        st.markdown("---")
        # Build Report
        st.markdown("## 🌾 Full Analysis Report")
        
        # Crop & Disease Summary
        col_crop, col_disease = st.columns(2)
        with col_crop:
            st.markdown(f"### 🧬 Crop Identified")
            st.write(res.get("crop_name", "Unknown"))
        with col_disease:
            st.markdown(f"### 🛑 Disease Status")
            st.write(res.get("disease_name", "Healthy"))
        
        st.markdown("---")
        
        st.markdown("## 🧠 Condition Assessment")
        st.write(res.get("description", "No description
