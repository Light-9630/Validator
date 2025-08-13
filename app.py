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
st.markdown("---")

# === SETTINGS ===
with st.sidebar:
    st.header("⚙ Settings")
    threads = st.number_input("Number of concurrent threads", min_value=1, max_value=100, value=20)
    rate_limit_delay = st.number_input("Delay between requests (seconds)", min_value=0.0, max_value=5.0, value=0.2)
    check_type = st.radio(
        "📄 File Type to Check",
        options=["ads.txt", "app-ads.txt"],
        index=0,
    )
st.markdown("---")

# ===== HELPER FUNCTIONS =====
@st.cache_data
def read_lines_from_file(file):
    """Reads lines from an uploaded file, handling different encodings."""
    try:
        content = file.read().decode("utf-8-sig", errors="replace")
        return [line.strip() for line in content.splitlines() if line.strip()]
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return []

def read_lines_from_textarea(text):
    """Reads lines from a text area."""
    return [line.strip() for line in text.splitlines() if line.strip()]

def normalize_ads_line(line):
    """Normalizes an ads.txt line for consistent comparison."""
    line = line.strip().lower()
    if line.startswith("#"):
        return ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 3:
        # Keep second part as is (publisher ID), normalize others
        parts[0] = parts[0].lower()
        parts[2] = parts[2].lower()
    return ",".join(parts)

# ===== REQUEST SESSION SETUP =====
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.100 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
}

# ===== CORE FUNCTIONS =====
def fetch_ads_txt(domain, filename, use_https=True):
    """Fetches the ads file, with a fallback to HTTP."""
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
        return "ERROR: Timeout"
    except requests.exceptions.SSLError:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        return "ERROR: SSL Error"
    except requests.exceptions.ConnectionError:
        if use_https:
            return fetch_ads_txt(domain, filename, use_https=False)
        return "ERROR: Connection Failed"
    except requests.exceptions.HTTPError as e:
        if use_https and e.response.status_code != 404: # Don't retry on 404
            return fetch_ads_txt(domain, filename, use_https=False)
        return f"ERROR: HTTP Error {e.response.status_code}"
    except Exception as e:
        return f"ERROR: {str(e)}"

def check_ads_txt(domain, entries_to_check, filename):
    """Checks for specified entries within a domain's ads file."""
    ads_content = fetch_ads_txt(domain, filename)
    result = {"domain": domain}
    
    if ads_content.startswith("ERROR"):
        for entry in entries_to_check:
            result[entry] = ads_content
        return result

    ads_lines = {
        normalize_ads_line(line)
        for line in ads_content.splitlines()
        if normalize_ads_line(line)
    }
    
    for entry in entries_to_check:
        normalized_entry = normalize_ads_line(entry)
        match_found = normalized_entry in ads_lines
        result[entry] = "YES" if match_found else "NO"
    return result

st.markdown("---")

# ===== UI INPUTS =====
tab1, tab2 = st.tabs(["🌐 Domains", "📜 Ads.txt Entries"])
with tab1:
    with st.expander("📂 Upload a domains file (.csv or .txt)"):
        domains_file = st.file_uploader("Upload Domains", type=["csv", "txt"])
    st.info("OR")
    with st.expander("✏ Paste a list of domains"):
        domains_paste = st.text_area("Paste one domain per line here", height=150)

with tab2:
    with st.expander("📂 Upload an entries file (.csv or .txt)"):
        lines_file = st.file_uploader("Upload Ads.txt Entries", type=["csv", "txt"])
    st.info("OR")
    with st.expander("✏ Paste a list of ads.txt entries"):
        lines_paste = st.text_area("Paste one entry per line here", height=150)

st.markdown("---")
# ===== RUN CHECKER =====
if st.button("🚀 Run Checker", use_container_width=True):
    if not (domains_file or domains_paste) or not (lines_file or lines_paste):
        st.error("⚠ Please provide both Domains and Ads.txt entries.")
    else:
        start_time = datetime.now()
        
        # Load and normalize data
        domains = []
        if domains_file:
            domains = read_lines_from_file(domains_file)
        if not domains and domains_paste:
            domains = read_lines_from_textarea(domains_paste)
        domains = [d for d in domains if d]

        entries_to_check = []
        if lines_file:
            entries_to_check = read_lines_from_file(lines_file)
        if not entries_to_check and lines_paste:
            entries_to_check = read_lines_from_textarea(lines_paste)
        entries_to_check = [e for e in entries_to_check if e]

        if not domains or not entries_to_check:
            st.error("⚠ Invalid input. Please check your domains and entries.")
        else:
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {executor.submit(check_ads_txt, d, entries_to_check, check_type): d for d in domains}
                total = len(futures)
                for i, future in enumerate(as_completed(futures)):
                    results.append(future.result())
                    progress_bar.progress((i + 1) / total)
                    status_text.text(f"✅ Checked {i+1}/{total} domains...")
            
            df_results = pd.DataFrame(results)

            # --- Summary Metrics ---
            yes_count = (df_results == "YES").sum().sum()
            no_count = (df_results == "NO").sum().sum()
            error_count = df_results.apply(lambda row: row.astype(str).str.startswith("ERROR").sum(), axis=1).sum()
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Domains", len(domains))
            col2.metric("✅ YES", yes_count)
            col3.metric("❌ NO", no_count)
            col4.metric("⚠ Errors", error_count)
            
            st.markdown("---")

            # --- Results Table ---
            def color_cells(val):
                if val == "YES": return "background-color: #4CAF50; color: white;"
                if val == "NO": return "background-color: #F44336; color: white;"
                if str(val).startswith("ERROR"): return "background-color: #FF9800; color: white;"
                return ""

            st.dataframe(df_results.style.applymap(color_cells), use_container_width=True)
            
            # --- Download CSV ---
            output_csv = io.BytesIO()
            df_results.to_csv(output_csv, index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 Download Results CSV",
                data=output_csv.getvalue(),
                file_name=f"{check_type}_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

            st.success(f"✅ Checker finished! Time taken: {datetime.now() - start_time}")
