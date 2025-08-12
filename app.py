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

# Upload files
domains_file = st.file_uploader("Upload domains.csv (one domain per line)", type=["csv", "txt"])
lines_file = st.file_uploader("Upload lines.csv (ads.txt entries to check)", type=["csv", "txt"])

# Helper functions
def read_lines_flexible(file):
    content = file.read().decode("utf-8-sig", errors="ignore")
    return [line.strip() for line in content.splitlines() if line.strip()]

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

# Run button
if st.button("🚀 Run Checker") and domains_file and lines_file:
    start_time = datetime.now()

    domains = [strip_quotes(d).replace("\xa0", " ") for d in read_lines_flexible(domains_file)]
    entries_to_check = [strip_quotes(e).replace("\xa0", " ").lower() for e in read_lines_flexible(lines_file)]

    with ThreadPoolExecutor(max_workers=threads) as executor:
        results = list(executor.map(lambda d: check_ads_txt(d, entries_to_check), domains))

    df_results = pd.DataFrame(results)

    # Show table
    st.dataframe(df_results)

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
