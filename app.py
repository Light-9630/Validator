import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
from datetime import datetime

# === GLOBAL CONFIG ===
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# User-Agent to bypass blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0.0.0 Safari/537.36"
}

# Requests session with retry
def make_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

session = make_session()

# === INPUTS ===
st.sidebar.header("⚙ Settings")
mode = st.sidebar.radio("Search Mode", ["Strict (domain+id+relation)", "Flexible (domain+id only)"])
target = st.sidebar.radio("Target File", ["ads.txt", "app-ads.txt"])
threads = st.sidebar.slider("Threads", 1, 20, 5)

domains_text = st.text_area("Paste domains where search will happen (one per line)", height=150)
lines_text = st.text_area("Paste lines to check (domain, id, relation)", height=200)

# Parse inputs
def parse_lines(text):
    rows = []
    for raw in text.strip().splitlines():
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            rows.append(parts)
    return rows

domains = [d.strip() for d in domains_text.strip().splitlines() if d.strip()]
check_lines = parse_lines(lines_text)

# Show parsed lines as editable table
if check_lines:
    st.subheader("📝 Parsed Lines")
    df_input = pd.DataFrame(check_lines, columns=["Domain", "Publisher ID", "Relation"][:max(len(r) for r in check_lines)])
    st.dataframe(df_input, use_container_width=True)
else:
    df_input = None

# === FETCH ads.txt ===
def fetch_ads(domain):
    url = f"http://{domain}/{target}"
    try:
        resp = session.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.text.splitlines()
    except Exception:
        return []
    return []

# === CHECK MATCH ===
def check_domain(domain, lines):
    ads_lines = fetch_ads(domain)
    results = []
    for line in lines:
        if mode.startswith("Strict") and len(line) >= 3:
            d, pid, rel = line[0], line[1], line[2]
            match = any(
                d.lower() in l.lower() and pid in l and rel.lower() in l.lower()
                for l in ads_lines
            )
        else:  # Flexible
            if len(line) >= 2:
                d, pid = line[0], line[1]
                match = any(d.lower() in l.lower() and pid in l for l in ads_lines)
            else:
                match = False
        results.append("YES" if match else "NO")
    return results

# === RUN CHECK ===
if st.button("🚀 Run Checker"):
    if not domains or df_input is None:
        st.error("Please paste both domains and lines.")
    else:
        final_rows = []
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = {ex.submit(check_domain, dom, check_lines): dom for dom in domains}
            for f in as_completed(futures):
                dom = futures[f]
                try:
                    row = [dom] + f.result()
                except Exception:
                    row = [dom] + ["ERROR"] * len(check_lines)
                final_rows.append(row)

        # Build output DataFrame
        colnames = ["domain"] + [", ".join(line) for line in check_lines]
        df_out = pd.DataFrame(final_rows, columns=colnames)

        st.subheader("✅ Results")
        st.dataframe(df_out, use_container_width=True)

        # CSV Export
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_name = f"ads_checker_{ts}.csv"
        csv = df_out.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, file_name=csv_name, mime="text/csv")
