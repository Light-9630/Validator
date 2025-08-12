import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import io, time
from requests.adapters import HTTPAdapter, Retry

st.set_page_config(page_title="Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt Bulk Checker")

# === SETTINGS ===
threads = st.number_input("Number of threads", min_value=1, max_value=100, value=20)
rate_limit_delay = st.number_input("Delay between requests (seconds)", min_value=0.0, max_value=5.0, value=0.2)

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

# Create a session with retry logic
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504, 429])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

def fetch_ads_txt(domain, use_https=True):
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{domain}/ads.txt"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive"
    }

    try:
        time.sleep(rate_limit_delay)  # Rate limiting
        r = session.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        return r.text

    except requests.exceptions.Timeout:
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise Exception("Timeout")
    except requests.exceptions.SSLError:
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise Exception("SSL Error")
    except requests.exceptions.ConnectionError:
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise Exception("Connection Failed")
    except requests.exceptions.HTTPError as e:
        # Agar HTTPS pe 403 aaye toh HTTP try kare
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise Exception(f"HTTP Error: {e}")
    except Exception as e:
        if use_https:
            return fetch_ads_txt(domain, use_https=False)
        else:
            raise e


def check_ads_txt(domain, entries_to_check):
    try:
        ads_content = fetch_ads_txt(domain)

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
            entries_to_check = [strip_quotes(e).replace("\xa0", " ") for e in read_lines_from_file(lines_file)]
        else:
            entries_to_check = [strip_quotes(e).replace("\xa0", " ") for e in read_lines_from_textarea(lines_paste)]

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


