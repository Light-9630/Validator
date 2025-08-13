import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import io
from requests.adapters import HTTPAdapter, Retry

# === PAGE CONFIG ===
st.set_page_config(page_title="Ads.txt / App-Ads.txt Bulk Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === INPUT: THREAD COUNT ===
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=50, value=10)

# === INPUT: BULK PASTE ===
paste_input = st.text_area("📋 Paste domains (one per line)", height=200)

# === INPUT: FILE UPLOAD ===
uploaded_file = st.file_uploader("📂 Or upload a file (.txt or .csv)", type=["txt", "csv"])

# === TARGET LINES TO SEARCH ===
lines_input = st.text_area("🔍 Lines to search in ads.txt/app-ads.txt (one per line)", height=150)

# === PARSE INPUT DOMAINS ===
domains = []
if paste_input.strip():
    domains += [d.strip() for d in paste_input.strip().split("\n") if d.strip()]

if uploaded_file:
    if uploaded_file.name.endswith(".txt"):
        domains += [line.strip() for line in uploaded_file.read().decode().split("\n") if line.strip()]
    elif uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        for col in df.columns:
            domains += [str(x).strip() for x in df[col] if str(x).strip()]

domains = list(set(domains))  # remove duplicates

# === PREPARE LINES TO SEARCH ===
search_lines = [line.strip() for line in lines_input.strip().split("\n") if line.strip()]

# === HTTP SESSION WITH RETRIES ===
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))

# === FETCH ADS.TXT / APP-ADS.TXT ===
def fetch_ads(domain):
    urls = [
        f"https://{domain}/ads.txt",
        f"https://{domain}/app-ads.txt",
        f"http://{domain}/ads.txt",
        f"http://{domain}/app-ads.txt"
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=5)
            if r.status_code == 200 and len(r.text) > 0:
                return domain, url, r.text.lower()
        except requests.RequestException:
            pass
    return domain, None, None

results = []
if st.button("🚀 Run Check"):
    if not domains:
        st.error("❌ Please provide at least one domain.")
    elif not search_lines:
        st.error("❌ Please provide lines to search.")
    else:
        progress = st.progress(0)
        data = []

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(fetch_ads, d): d for d in domains}
            total = len(futures)
            for i, future in enumerate(as_completed(futures)):
                domain, url, content = future.result()
                row = {"Page": url if url else domain}
                for line in search_lines:
                    if content and line.lower() in content:
                        row[line] = "Yes"
                    else:
                        row[line] = "No"
                data.append(row)
                progress.progress((i + 1) / total)

        df_out = pd.DataFrame(data)
        st.dataframe(df_out)

        # === DOWNLOAD CSV ===
        csv = df_out.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
