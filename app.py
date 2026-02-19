import base64
import io
import json
import os
from datetime import datetime
import time

import requests
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
from PIL import Image

# ================= CONFIG ================= #
# API key intentionally kept in-code per requirement.
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-nano-12b-v2-vl:free"
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
REASONING_MODEL = "openai/gpt-oss-120b:free"
USER_DB = "users.json"
EXPORT_DIR = "exports"

# ================= ACTION MAP ================= #
ACTION_MAP = {
    "Soil moisture modeling": "Analyze soil moisture modeling with sensor + weather assumptions and actionable irrigation guidance.",
    "Water requirement prediction": "Predict farm water requirement for next 14 days by crop stage and weather uncertainty.",
    "AI-driven irrigation schedule": "Create AI-driven irrigation schedule with time windows and liters/acre.",
    "Drought early warning": "Generate drought early warning indicators for 30 days.",
    "Water waste optimization %": "Estimate current water waste percentage and optimization opportunities.",
    "NPK prediction": "Predict nitrogen, phosphorus, potassium levels and corrective plan.",
    "pH imbalance detection": "Detect pH imbalance and recommend treatment protocol.",
    "Nutrient deficiency fusion": "Use leaf + soil fusion assumptions to identify nutrient deficiencies.",
    "Fertilizer recommendation": "Build fertilizer recommendation engine output for this farm.",
    "Long-term soil health score": "Estimate long-term soil health score and yearly action plan.",
    "Insect classification": "Classify likely insects and risk level by season.",
    "Pest density estimation": "Estimate pest density per acre with intervention threshold.",
    "Swarm detection": "Detect swarm risk and alert plan.",
    "Migration pattern prediction": "Predict wind-based pest migration pattern over 7 days.",
    "Smart pesticide timing": "Recommend ideal pesticide application timing.",
    "Satellite imagery integration": "Provide satellite imagery integration plan and inferred crop signals.",
    "Growth stage tracking": "Track crop growth stage and next milestones.",
    "Production estimate per acre": "Estimate production per acre with confidence range.",
    "Profit forecast": "Generate profit forecast using yield, costs, and market price assumptions.",
    "Market price integration": "Integrate market price trend and suggest sell timing.",
    "Camera→Analyze→Recommend→Auto-execute": "Design camera-to-execution pipeline with automation gates.",
    "Irrigation valve control": "Generate irrigation valve control logic and failsafe.",
    "Sprayer control": "Generate smart sprayer control strategy.",
    "Drone-based spraying": "Plan drone-based spraying route and timing.",
    "Automated farm reporting": "Create automated farm reporting template and KPI plan.",
    "Multi-modal fusion model": "Design fusion model: Vision + Weather + Soil + Time.",
    "Disease risk 7-30 days": "Predict disease risk for 7-30 days using humidity + temperature.",
    "Frost risk alerts": "Predict frost risk and preventive actions.",
    "Heat stress prediction": "Predict heat stress windows and protection actions.",
    "Crop growth stage mapping": "Generate crop growth stage map from multimodal data.",
    "Price prediction AI": "Calculate total crop production cost and expected local market gain/profit.",
    "Full Agent Pipeline": "Build one proper end-to-end AI agent pipeline using Vision/Climate/Soil/Water/Market/Execution layers.",
}


def call_openrouter(messages, model=REASONING_MODEL):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        
        # 🔥 Check status first
        if response.status_code != 200:
            return f"HTTP Error {response.status_code}: {response.text}"

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
        "menu_choice": "Home",
        "agent_status": "Idle",
        "task_queue": [],
        "reports": [],
        "chat_history": [],
        "detection_result": None,
        "location": "",
        "cost_estimation": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value




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






def home_page():
    st.markdown("## 🌾 Agricultural Intelligence Dashboard")

    uploaded_image = st.file_uploader("Upload Leaf Image", type=["jpg", "jpeg", "png"])

    if uploaded_image:
        image = Image.open(uploaded_image)
        st.image(image, use_container_width=True)

        if st.button("Analyze"):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            img_bytes = buffer.getvalue()

            with st.spinner("Running full intelligence pipeline..."):
                result = run_reasoning_model(
                    img_bytes,
                    {"location": st.session_state.location}
                )

            st.session_state.detection_result = result

    if st.session_state.detection_result:
        res = st.session_state.detection_result

        st.markdown("---")
        st.markdown("### 🧬 Crop Identified")
        st.write(res.get("crop_name", "Unknown"))

        st.markdown("### 🛑 Disease Status")
        st.write(res.get("disease_name", "Healthy"))

        st.markdown("---")

        st.markdown("### 🧠 Description")
        st.write(res.get("description", ""))

        st.markdown("### 🛠 Solution")
        st.write(res.get("solution", ""))

        st.markdown("### 🧪 Fertilizers")
        st.write(res.get("fertilizers", ""))

        st.markdown("### 📊 Soil Insights")
        st.write(res.get("soil_insights", ""))

        st.markdown("### 💧 Water Forecast")
        st.write(res.get("water_forecast", ""))

        st.markdown("### 📈 Risk Level")
        st.write(res.get("risk_score", ""))


def chat_page():
    st.title("💬 Agent Chat")
    
    # Chat container for scrollable messages
    chat_container = st.container()
    
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg['role']):
                st.markdown(f"*{msg['time']}*")
                st.write(msg['text'])

    query = st.chat_input("Ask about farming, costs, irrigation, market, disease...")
    if query:
        st.session_state.chat_history.append(
            {"time": datetime.now().strftime("%H:%M:%S"), "role": "user", "text": query}
        )
        with st.spinner("Agent is thinking..."):
            answer = call_openrouter(
                [
                    {"role": "system", "content": "You are a practical agricultural AI agent."},
                    {"role": "user", "content": query},
                ]
            )
        st.session_state.chat_history.append(
            {"time": datetime.now().strftime("%H:%M:%S"), "role": "assistant", "text": answer}
        )
        st.rerun()


def shop_or_doctors_page(title, actor):
    st.title(title)
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        crop = st.text_input(f"{actor}: Crop name")
    with col_in2:
        requirement = st.text_input(f"{actor}: Requirement")

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Search {actor}"):
            with st.spinner(f"Finding the best {actor.lower()}s for you..."):
                location = st.session_state.get('location', 'unknown location')
                search_prompt = f"As an agricultural AI, find/recommend 5 {actor.lower()}s or services for {crop} with requirement: {requirement} near {location}. Provide name, contact detail (simulated), and specialized service. Format as a clean list."
                response = call_openrouter([{"role": "user", "content": search_prompt}])
                if "error" not in response.lower() or "401" not in response:
                    st.success(f"Found {actor}s!")
                    st.markdown(response)
                else:
                    st.error(f"Search failed: {response}")

    with col2:
        if st.button("Show all nearby"):
            with st.spinner(f"Listing all major {actor.lower()} options..."):
                search_prompt = f"List all major {actor.lower()} options for {crop} farming. Include pricing estimates and usage summary."
                response = call_openrouter([{"role": "user", "content": search_prompt}])
                st.markdown(response)


def contact_page():
    st.title("📞 Contact")
    st.markdown(
        """
        **AI Farm Agent Team**  
        Email: support@aifarmagent.local  
        Services: Vision, Climate, Soil, Water, Market, Execution  
        """
    )


def show_reports_panel():
    st.markdown("## 📊 Generated Reports")
    if not st.session_state.reports:
        st.info("No reports yet. Run analyses from the left panel.")
        return
    for report in st.session_state.reports[:12]:
        with st.expander(f"{report['time']} — {report['title']}"):
            st.write(report["content"])


def main():
    st.set_page_config(page_title="Agri Super Agent", layout="wide")
    ensure_session_defaults()

    run_all_background_tasks()

    # ---------- TOP NAVBAR ----------
    nav_cols = st.columns(5)

    menu_items = ["Home", "Chat", "Shop", "Doctors", "Contact"]

    for i, item in enumerate(menu_items):
        if nav_cols[i].button(
            item,
            use_container_width=True,
            type="primary" if st.session_state.menu_choice == item else "secondary"
        ):
            st.session_state.menu_choice = item
            st.rerun()

    st.markdown("---")

    # ---------- MAIN LAYOUT ----------
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("## 🧠 Agent Panel")
        st.write(f"Status: {st.session_state.agent_status}")
        st.markdown("---")

        st.subheader("📍 Farm Info")
        st.session_state.location = st.text_input("Farm location")

        st.markdown("---")

        st.subheader("⚙ Quick Actions")

        selected_action = st.selectbox("Select analysis", list(ACTION_MAP.keys()))

        if st.button("Run Analysis", use_container_width=True):
            queue_task(selected_action, ACTION_MAP[selected_action])
            st.success("Queued.")

        if st.button("Run Full Pipeline", use_container_width=True):
            for action, prompt in ACTION_MAP.items():
                queue_task(action, prompt)
            st.success("Full pipeline queued.")

    with right_col:

        menu = st.session_state.menu_choice

        if menu == "Home":
            home_page()
        elif menu == "Chat":
            chat_page()
        elif menu == "Shop":
            shop_or_doctors_page("🛒 Fertilizer Shop", "Shop")
        elif menu == "Doctors":
            shop_or_doctors_page("🩺 Doctors", "Doctors")
        else:
            contact_page()

    if st.session_state.cost_estimation:
        est = st.session_state.cost_estimation
        st.markdown("---")
        st.markdown("## 📊 Cost & Profit Estimation Report")

        # Try JSON parse if AI returned text
        try:
            # Clean output in case of markdown blocks
            if "```json" in est:
                est = est.split("```json")[1].split("```")[0].strip()
            elif "```" in est:
                est = est.split("```")[1].split("```")[0].strip()
            
            est_json = json.loads(est)
        except:
            st.write("⚠️ Could not parse estimation. Raw output:")
            st.write(est)
            est_json = None

        if est_json:
            st.write("### 📈 Local Market Price")
            st.write(est_json.get("market_price","N/A"))

            st.write("### 📅 Price Trend & Best Months")
            st.write(est_json.get("price_trend",""))
            st.write("Best Months to Sell:", est_json.get("best_months", []))

            st.write("### 💰 Cost & Revenue Breakdown")
            st.write(f"Total Production Cost: {est_json.get('total_cost','')}")
            st.write(f"Expected Revenue: {est_json.get('expected_revenue','')}")
            st.write(f"Profit/Loss: {est_json.get('profit_or_loss','')}")

            st.write("### 🚚 Travel Costs")
            st.write(est_json.get("travel_costs",""))

            st.write("### 🧠 Recommendation")
            st.info(est_json.get("recommendation",""))

    show_reports_panel()


if __name__ == "__main__":
    main()
