import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import io

st.set_page_config(page_title="Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt Bulk Checker")

# === SETTINGS ===
threads = st.number_input("Number of threads", min_value=1, max_value=100, value=20)

# ===== INPUT METHODS =====
st.subheader("1️⃣ Domains List")
domains_file = st.file_uploader("Upload domains.csv/txt (one domain per line)", type=["csv", "txt"])
domains_paste = st.text_area("Or paste domains here (one per line)", height=150)

st.subheader("2️⃣ Ads.txt Entries to Check")
lines_file = st.file_uploader("Upload lines.csv/txt (entries to check)", type=["csv", "txt"])
lines_paste = st.text_area("Or paste ads.txt entries here (one per line)", height=150)

# ===== HELPER FUNCTIONS =====
def read_lines_from_file(file):
    content = file.read().decode("utf-8-sig", errors="ignore")
    return [line.strip() for line in content.splitlines() if line.strip()]

def read_lines_from_textarea(text):
    return [line.strip() for line in text.splitlines() if line.strip()]

def strip_quotes(s):
    if len(s) >= 2 and ((s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))):
        return s[1:-1]
    return s

def fetch_ads_txt(domain, use_https=True):
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{domain}/ads.txt"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.text
    except Exception:
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise

def check_ads_txt(domain, entries_to_check):
    try:
        ads_content = fetch_ads_txt(domain)

        ads_lines_with_space = [
            line.strip().lower()
            for line in ads_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        ads_lines_no_space = [line.replace(" ", "") for line in ads_lines_with_space]

        result = {"domain": domain}
        for entry in entries_to_check:
            entry_with_space = entry.strip().lower()
            entry_no_space = entry_with_space.replace(" ", "")

            match_found = (
                any(line.startswith(entry_with_space) for line in ads_lines_with_space)
                or any(line.startswith(entry_no_space) for line in ads_lines_no_space)
            )

            result[entry] = "YES" if match_found else "NO"

        return result

    except Exception as e:
        result = {"domain": domain}
        for entry in entries_to_check:
            result[entry] = f"ERROR: {str(e)}"
        return result

# ===== RUN CHECKER =====
if st.button("🚀 Run Checker"):
    if not (domains_file or domains_paste) or not (lines_file or lines_paste):
        st.error("⚠ Please provide both Domains and Ads.txt entries (either upload or paste).")
    else:
        start_time = datetime.now()

        # Load domains
        if domains_file:
            domains = [strip_quotes(d).replace("\xa0", " ") for d in read_lines_from_file(domains_file)]
        else:
            domains = [strip_quotes(d).replace("\xa0", " ") for d in read_lines_from_textarea(domains_paste)]

        # Load ads.txt entries
        if lines_file:
            entries_to_check = [strip_quotes(e).replace("\xa0", " ").lower() for e in read_lines_from_file(lines_file)]
        else:
            entries_to_check = [strip_quotes(e).replace("\xa0", " ").lower() for e in read_lines_from_textarea(lines_paste)]

        with st.spinner("⏳ Checking domains... Please wait."):
            with ThreadPoolExecutor(max_workers=threads) as executor:
                results = list(executor.map(lambda d: check_ads_txt(d, entries_to_check), domains))

        df_results = pd.DataFrame(results)

        # Show table
        st.dataframe(df_results, use_container_width=True)

        # Download CSV
        output_csv = io.BytesIO()
        df_results.to_csv(output_csv, index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 Download Results CSV",
            data=output_csv.getvalue(),
            file_name=f"ads_check_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

        st.success(f"✅ Done! Time taken: {datetime.now() - start_time}")
