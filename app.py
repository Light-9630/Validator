import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
from requests.adapters import HTTPAdapter, Retry

st.set_page_config(page_title="📄 Ads.txt Bulk Checker", layout="wide")
st.title("📄 Ads.txt Bulk Checker")

# === SETTINGS ===
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=50, value=10)

# === FUNCTIONS ===
def normalize_ads_line(line):
    parts = [p.strip() for p in line.split(',')]
    for i in range(len(parts)):
        if i != 1:  # Keep seller ID (2nd value) as is
            parts[i] = parts[i].lower()
    return ",".join(parts)

def fetch_ads_txt(domain):
    url = f"https://{domain}/ads.txt"
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    try:
        response = session.get(url, timeout=5)
        if response.status_code == 200:
            return response.text.splitlines()
        else:
            return []
    except Exception:
        return []

def check_ads_txt(domain, search_line):
    ads_lines = fetch_ads_txt(domain)
    ads_norm = [normalize_ads_line(l) for l in ads_lines if l.strip()]
    search_norm = normalize_ads_line(search_line)
    return "YES" if search_norm in ads_norm else "NO"

# === FILE UPLOAD ===
uploaded_lines = st.file_uploader("Upload lines.csv (Domain, Search Line)", type=["csv"])

if uploaded_lines:
    df = pd.read_csv(uploaded_lines)
    start_time = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=threads) as executor:
        future_to_row = {
            executor.submit(check_ads_txt, row[0], row[1]): row
            for _, row in df.iterrows()
        }
        for future in as_completed(future_to_row):
            row = future_to_row[future]
            try:
                result = future.result()
            except Exception:
                result = "ERROR"
            results.append((row[0], row[1], result))

    # Save with timestamp
    output_df = pd.DataFrame(results, columns=["Domain", "Search Line", "Exists"])
    output_filename = f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_df.to_csv(output_filename, index=False)

    st.success(f"✅ Done! Time taken: {time.time() - start_time:.2f} seconds")
    st.download_button("📥 Download Results", data=output_df.to_csv(index=False), file_name=output_filename, mime="text/csv")
