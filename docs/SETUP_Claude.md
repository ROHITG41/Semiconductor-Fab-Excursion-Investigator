# Setup (Windows, VS Code terminal)

```
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (then add GEMINI_API_KEY and FAB_SENTRY_HMAC_SECRET)
python simulator.py
python check_setup.py
streamlit run app.py
```

- Create the HMAC secret with: `python -c "import secrets; print(secrets.token_hex(32))"`
- Record real runs for Replay mode: `python record_trace.py --scenario S01` (or `--all`)
- Public demo mode: set `FAB_SENTRY_PUBLIC_DEMO=1` (on Streamlit Cloud, under Secrets). The app then offers only Replay and Scripted modes, hides Live Gemini and sign-off, and reads recorded runs from `demo_traces/` (create them with `python make_demo_traces.py`).
- Never commit `.env`. It holds your keys.

For help running this on your own data, get in touch: grohit41@gmail.com
