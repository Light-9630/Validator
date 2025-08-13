import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import io, time
from requests.adapters import HTTPAdapter, Retry

# === PAGE CONFIG ===
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === SETTINGS ===
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=100, value=20)
rate_limit_delay = st.number_input("🐢 Delay between requests (seconds)", min_value=0.0, max_value=5.0, value=0.2)
check_type = st.radio(
    "📄 File Type to Check",
    options=["ads.txt", "app-ads.txt"],
    index=0,
    horizontal=True
)

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

# Create session with retry + UA
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[403, 429, 500, 502, 503, 504],
    raise_on_status=False
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/127.0.6533.100 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ===== FETCH FUNCTION =====
def fetch_ads_txt(domain, filename="ads.txt", use_https=True):
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{domain}/{filename}"
    try:
        time.sleep(rate_limit_delay)
        r = session.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        return r.text
    except requests.exceptions.Timeout:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        else:
            raise Exception("Timeout")
    except requests.exceptions.SSLError:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        else:
            raise Exception("SSL Error")
    except requests.exceptions.ConnectionError:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        else:
            raise Exception("Connection Failed")
    except requests.exceptions.HTTPError as e:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        else:
            raise Exception(f"HTTP Error: {e}")
    except Exception as e:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        else:
            raise e

# ===== CHECK FUNCTION =====
def check_ads_txt(domain, entries_to_check, filename):
    try:
        ads_content = fetch_ads_txt(domain, filename)
        ads_lines_with_space = [
            line.strip()
            for line in ads_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        ads_lines_no_space = [line.replace(" ", "") for line in ads_lines_with_space]
        result = {"domain": domain}
        for entry in entries_to_check:
            entry_with_space = entry.strip()
            entry_no_space = entry_with_space.replace(" ", "")
            match_found = (
                any(line.startswith(entry_with_space) for line in ads_lines_with_space)
                or any(line.startswith(entry_no_space) for line in ads_lines_no_space)
            )
            result[entry] = "YES" if match_found else "NO"
        return result
    except Exception as e:
        return {"domain": domain, **{entry: f"ERROR: {str(e)}" for entry in entries_to_check}}

# ===== UI INPUTS =====
tab1, tab2 = st.tabs(["🌐 Domains", "📜 Ads.txt Entries"])

with tab1:
    with st.expander("📂 Upload domains.csv/txt"):
        domains_file = st.file_uploader("Upload Domains", type=["csv", "txt"])
    with st.expander("✏ Paste domains"):
        domains_paste = st.text_area("Paste domains here", height=150)

with tab2:
    with st.expander("📂 Upload entries.csv/txt"):
        lines_file = st.file_uploader("Upload Ads.txt Entries", type=["csv", "txt"])
    with st.expander("✏ Paste entries"):
        lines_paste = st.text_area("Paste ads.txt entries here", height=150)

# ===== RUN CHECKER =====
if st.button("🚀 Run Checker"):
    if not (domains_file or domains_paste) or not (lines_file or lines_paste):
        st.error("⚠ Please provide both Domains and Ads.txt entries.")
    else:
        start_time = datetime.now()

        # Load data
        if domains_file:
            domains = [strip_quotes(d).replace("\xa0", " ") for d in read_lines_from_file(domains_file)]
        else:
            domains = [strip_quotes(d).replace("\xa0", " ") for d in read_lines_from_textarea(domains_paste)]

        if lines_file:
            entries_to_check = [strip_quotes(e).replace("\xa0", " ") for e in read_lines_from_file(lines_file)]
        else:
            entries_to_check = [strip_quotes(e).replace("\xa0", " ") for e in read_lines_from_textarea(lines_paste)]

        # Progress + results
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_ads_txt, d, entries_to_check, check_type): d for d in domains}
            total = len(futures)
            for i, future in enumerate(as_completed(futures)):
                results.append(future.result())
                progress_bar.progress((i + 1) / total)
                status_text.text(f"✅ Checked {i+1}/{total} domains")

        df_results = pd.DataFrame(results)

        # Summary counts
        yes_count = (df_results == "YES").sum().sum()
        no_count = (df_results == "NO").sum().sum()
        error_count = df_results.apply(lambda row: row.astype(str).str.startswith("ERROR").sum(), axis=1).sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Domains", len(domains))
        col2.metric("✅ YES", yes_count)
        col3.metric("❌ NO", no_count)
        col4.metric("⚠ Errors", error_count)

        # Color table
        def color_cells(val):
            if val == "YES":
                return "background-color: #4CAF50; color: white;"
            elif val == "NO":
                return "background-color: #F44336; color: white;"
            elif str(val).startswith("ERROR"):
                return "background-color: #FF9800; color: white;"
            return ""

        st.dataframe(df_results.style.applymap(color_cells), use_container_width=True)

        # Download CSV
        output_csv = io.BytesIO()
        df_results.to_csv(output_csv, index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 Download Results CSV",
            data=output_csv.getvalue(),
            file_name=f"{check_type}_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

        st.success(f"✅ Done! Time taken: {datetime.now() - start_time}")

