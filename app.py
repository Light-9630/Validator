import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime
from requests.adapters import HTTPAdapter, Retry

# ============ SETTINGS ============
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# --- Retry adapter for robust requests ---
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500,502,503,504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))

# --- Sidebar options ---
mode = st.sidebar.radio("Search Mode:", ["Flexible (Domain+ID)", "Strict (Domain+ID+Relation)"])
file_type = st.sidebar.radio("File to Check:", ["ads.txt", "app-ads.txt"])

# --- Input for domains where we fetch ads.txt ---
st.subheader("1️⃣ Paste domains where we will fetch ads.txt/app-ads.txt")
domains_input = st.text_area("Enter domains (one per line)", height=150)

# --- Input for lines to check ---
st.subheader("2️⃣ Paste ads.txt/app-ads.txt lines to check")
lines_input = st.text_area("Enter lines (domain,id,relation,extra...)", height=200)

if st.button("Run Checker"):
    if not domains_input.strip() or not lines_input.strip():
        st.error("Please paste both domains and lines to check.")
    else:
        domains = [d.strip() for d in domains_input.strip().splitlines() if d.strip()]
        raw_lines = [l.strip() for l in lines_input.strip().splitlines() if l.strip()]

        # --- Normalize user lines into parts ---
        search_lines = []
        for line in raw_lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            search_lines.append(parts)

        # --- Create DataFrame skeleton ---
        columns = ["Domain"] + [", ".join(p) for p in search_lines]
        results = []

        # --- Check each domain ---
        for dom in domains:
            url = f"http://{dom}/{file_type}"
            try:
                headers = {"User-Agent": "Mozilla/5.0 (AdsCheckerBot)"}
                resp = session.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                else:
                    lines = []
            except Exception as e:
                lines = []

            row = {"Domain": dom}
            for parts in search_lines:
                found = False
                for l in lines:
                    lparts = [p.strip() for p in l.split(",")]
                    # Flexible match (only domain + id required)
                    if mode.startswith("Flexible"):
                        if len(parts) >= 2 and len(lparts) >= 2:
                            if parts[0] == lparts[0] and parts[1] == lparts[1]:
                                found = True
                                break
                    else:  # Strict match (domain + id + relation)
                        if len(parts) >= 3 and len(lparts) >= 3:
                            if parts[0] == lparts[0] and parts[1] == lparts[1] and parts[2] == lparts[2]:
                                found = True
                                break
                row[", ".join(parts)] = "YES" if found else "NO"
            results.append(row)

        df = pd.DataFrame(results, columns=columns)

        # --- Show & Save output ---
        st.subheader("✅ Results")
        st.dataframe(df, use_container_width=True)

        # Save to CSV
        fname = f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(fname, index=False)
        st.success(f"Results saved as {fname}")
        st.download_button("⬇ Download CSV", df.to_csv(index=False), file_name=fname, mime="text/csv")
