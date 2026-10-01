
# Cooling Tower AI Agent — Prototype

## What it does
1. Accepts cooling-tower operating data.
2. Calculates CoC from conductivity, chloride and hardness.
3. Runs transparent rule-based checks.
4. Produces investigation actions.
5. Stores readings in SQLite.
6. Shows historical trends.
7. Optionally uses an OpenAI model for technical reasoning.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optional AI reasoning
Set your API key before starting Streamlit.

Windows PowerShell:
```powershell
$env:OPENAI_API_KEY="YOUR_API_KEY"
streamlit run app.py
```

Without an API key, the deterministic rule engine and trend functions still work.

## Important
The limits in this prototype are DEMO values only. Replace them with the actual
customer operating envelope, Kurita product/SOP guidance, equipment design limits,
and validated engineering rules before operational use.
