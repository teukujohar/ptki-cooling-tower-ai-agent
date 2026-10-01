
import os
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

DB = "cooling_tower.db"

st.set_page_config(page_title="Cooling Tower AI Agent", page_icon="💧", layout="wide")

# ---------- Database ----------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    con = get_conn()
    con.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer TEXT NOT NULL,
        equipment TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        makeup_conductivity REAL,
        ct_conductivity REAL,
        makeup_chloride REAL,
        ct_chloride REAL,
        makeup_hardness REAL,
        ct_hardness REAL,
        ph REAL,
        temperature REAL,
        makeup_flow REAL,
        blowdown_flow REAL,
        chemical_dosing REAL
    )
    """)
    con.commit()
    con.close()

def seed_demo():
    con = get_conn()
    n = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    if n == 0:
        now = datetime.now()
        rows = []
        for i in range(30):
            day = now - timedelta(days=29-i)
            ct_cond = 1180 + i * 20 + (30 if i > 23 else 0)
            rows.append((
                "Customer Demo", "CT-01",
                day.strftime("%Y-%m-%d %H:%M:%S"),
                250, ct_cond, 30, 30*(ct_cond/250),
                50, 50*(ct_cond/250), 8.0 + (0.8 if i > 24 else 0.1),
                32 + (i % 3), 100, 8 if i < 25 else 5,
                1.0 if i < 25 else 1.3
            ))
        con.executemany("""
        INSERT INTO readings
        (customer,equipment,timestamp,makeup_conductivity,ct_conductivity,
         makeup_chloride,ct_chloride,makeup_hardness,ct_hardness,ph,
         temperature,makeup_flow,blowdown_flow,chemical_dosing)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        con.commit()
    con.close()

init_db()
seed_demo()

# ---------- Engineering rules ----------
def coc(ct, makeup):
    if makeup is None or makeup <= 0:
        return None
    return ct / makeup

def analyze(row):
    findings = []
    severity = "NORMAL"

    cc = coc(row["ct_conductivity"], row["makeup_conductivity"])
    ch = coc(row["ct_chloride"], row["makeup_chloride"])
    hd = coc(row["ct_hardness"], row["makeup_hardness"])

    if row["ct_conductivity"] > 1500:
        findings.append(("HIGH", "Cooling-tower conductivity is above the demo target of 1,500 µS/cm."))
        severity = "ATTENTION"

    if row["ph"] > 8.5:
        findings.append(("HIGH", "pH is above the demo upper reference of 8.5."))
        severity = "ATTENTION"

    if cc and ch and abs(ch-cc) >= 1.5:
        findings.append(("MEDIUM", f"Chloride CoC ({ch:.2f}) differs from conductivity CoC ({cc:.2f}) by ≥1.5. Verify sampling/measurement and water balance."))
        severity = "ATTENTION"

    if row["chemical_dosing"] > 1.2:
        findings.append(("MEDIUM", "Chemical dosing is above the demo reference of 1.2 relative units. Verify actual dosing rate and controller setpoint."))
        severity = "ATTENTION"

    if row["blowdown_flow"] < 6:
        findings.append(("MEDIUM", "Blowdown flow is below the demo reference of 6 units. Check valve, control and actual flow."))
        severity = "ATTENTION"

    actions = []
    if any("conductivity" in x[1].lower() for x in findings):
        actions += ["Verify conductivity with a calibrated portable meter.",
                    "Check blowdown valve, controller setpoint and actual blowdown flow."]
    if any("pH" in x[1] for x in findings):
        actions += ["Verify pH measurement and review chemical dosing rate/setpoint."]
    if any("Chloride CoC" in x[1] for x in findings):
        actions += ["Repeat chloride analysis and compare with makeup-water chloride."]
    if not actions:
        actions = ["Continue routine monitoring and trend review."]

    return {
        "severity": severity,
        "coc_conductivity": cc,
        "coc_chloride": ch,
        "coc_hardness": hd,
        "findings": findings,
        "actions": list(dict.fromkeys(actions))
    }

# ---------- Optional OpenAI reasoning ----------
def ai_reasoning(row, result):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return (
            "AI reasoning is not connected yet. The deterministic rule engine is active. "
            "Set OPENAI_API_KEY to enable LLM reasoning.\n\n"
            "Suggested reasoning based on rules:\n" +
            "\n".join(f"- {a}" for a in result["actions"])
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f"""
You are a water-treatment technical assistant. Analyze the following cooling-tower data.
Do not invent site-specific limits. Clearly distinguish calculated facts, hypotheses,
and recommended verification steps. Do not recommend changing chemical dosage blindly.

DATA:
{row.to_dict()}

CALCULATED:
Conductivity CoC={result['coc_conductivity']:.2f}
Chloride CoC={result['coc_chloride']:.2f}
Hardness CoC={result['coc_hardness']:.2f}

RULE FINDINGS:
{result['findings']}

Return:
1. Executive summary
2. Evidence
3. Possible causes (ranked by investigation priority, not certainty)
4. Verification steps
5. Recommended follow-up
"""
        resp = client.responses.create(model="gpt-5.6-mini", input=prompt)
        return resp.output_text
    except Exception as e:
        return f"AI reasoning error: {e}"

# ---------- UI ----------
st.title("💧 Cooling Tower AI Agent")
st.caption("Prototype — data validation → engineering rules → trend → AI reasoning → action plan")

with st.sidebar:
    st.header("Customer Input")
    customer = st.text_input("Customer", "Customer Demo")
    equipment = st.text_input("Equipment", "CT-01")

    st.subheader("Makeup Water")
    mcond = st.number_input("Conductivity (µS/cm)", min_value=0.1, value=250.0)
    mch = st.number_input("Chloride (mg/L)", min_value=0.0, value=30.0)
    mhd = st.number_input("Hardness (mg/L)", min_value=0.0, value=50.0)

    st.subheader("Cooling Tower")
    cond = st.number_input("Conductivity (µS/cm)", min_value=0.0, value=1800.0)
    ph = st.number_input("pH", min_value=0.0, max_value=14.0, value=8.4)
    ch = st.number_input("Chloride (mg/L)", min_value=0.0, value=220.0)
    hd = st.number_input("Hardness (mg/L)", min_value=0.0, value=310.0)
    temp = st.number_input("Temperature (°C)", value=32.0)
    makeup_flow = st.number_input("Makeup flow", min_value=0.0, value=100.0)
    blowdown_flow = st.number_input("Blowdown flow", min_value=0.0, value=8.0)
    dosing = st.number_input("Chemical dosing (relative units)", min_value=0.0, value=1.0)

    if st.button("Analyze Current Data", type="primary"):
        st.session_state["run"] = True

row = pd.Series({
    "customer": customer, "equipment": equipment,
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "makeup_conductivity": mcond, "ct_conductivity": cond,
    "makeup_chloride": mch, "ct_chloride": ch,
    "makeup_hardness": mhd, "ct_hardness": hd,
    "ph": ph, "temperature": temp, "makeup_flow": makeup_flow,
    "blowdown_flow": blowdown_flow, "chemical_dosing": dosing
})
result = analyze(row)

if st.session_state.get("run", False):
    st.subheader("1. Agent Status")
    status = result["severity"]
    st.metric("Overall Status", status)

    c1,c2,c3 = st.columns(3)
    c1.metric("CoC — Conductivity", f"{result['coc_conductivity']:.2f}")
    c2.metric("CoC — Chloride", f"{result['coc_chloride']:.2f}")
    c3.metric("CoC — Hardness", f"{result['coc_hardness']:.2f}")

    st.subheader("2. Detected Findings")
    if result["findings"]:
        for sev, msg in result["findings"]:
            st.warning(f"**{sev}:** {msg}")
    else:
        st.success("No rule-based abnormality detected.")

    st.subheader("3. Recommended Investigation")
    for i, action in enumerate(result["actions"], 1):
        st.write(f"**{i}.** {action}")

    st.subheader("4. AI Technical Reasoning")
    st.info(ai_reasoning(row, result))

    # Save reading
    if st.button("Save Reading to Local Database"):
        con = get_conn()
        con.execute("""
        INSERT INTO readings
        (customer,equipment,timestamp,makeup_conductivity,ct_conductivity,
         makeup_chloride,ct_chloride,makeup_hardness,ct_hardness,ph,
         temperature,makeup_flow,blowdown_flow,chemical_dosing)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, tuple(row.values))
        con.commit()
        con.close()
        st.success("Reading saved.")

st.divider()
st.subheader("5. Historical Trend")

con = get_conn()
hist = pd.read_sql_query(
    "SELECT * FROM readings WHERE customer=? AND equipment=? ORDER BY timestamp",
    con, params=(customer, equipment)
)
con.close()

if not hist.empty:
    hist["timestamp"] = pd.to_datetime(hist["timestamp"])
    hist["CoC"] = hist["ct_conductivity"] / hist["makeup_conductivity"]
    chart = hist.set_index("timestamp")[["ct_conductivity","ph","CoC"]]
    st.line_chart(chart)
    st.dataframe(hist.tail(10), use_container_width=True)
else:
    st.info("No historical data for this customer/equipment.")

st.caption("Prototype only. Engineering limits must be replaced with the actual site/Kurita SOP, chemical program and customer operating envelope before production use.")
