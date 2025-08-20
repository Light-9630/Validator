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
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=20, value=5)

# === FILE OR PASTE INPUT ===
uploaded_file = st.file_uploader("Upload ads.txt / app-ads.txt file", type=["txt", "csv"])
pasted_text = st.text_area("Or paste domains here (one per line)", height=150)

domains = []
if uploaded_file:
    domains = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()]
elif pasted_text:
    domains = [line.strip() for line in pasted_text.splitlines() if line.strip()]

# === SEARCH INPUT ===
lines_text = st.text_area("Paste lines to search (one per line)", height=150)
search_lines = [line.strip() for line in lines_text.splitlines() if line.strip()]

# === HEADER OPTIONS ABOVE PREVIEW ===
st.subheader("🔎 Preview Settings")
case_sensitive = {
    i: st.checkbox(f"Case Sensitive for Part {i+1}", value=False, key=f"cs_{i}")
    for i in range(4)
}

# === FUNCTION TO FETCH ADS.TXT ===
def fetch_ads(domain):
    urls = [f"https://{domain}/ads.txt", f"https://{domain}/app-ads.txt"]
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500,502,503,504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    for url in urls:
        try:
            resp = session.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return resp.text.splitlines()
        except Exception:
            continue
    return []

# === FUNCTION TO CHECK MATCHES ===
def check_domain(domain, search_lines):
    ads_lines = fetch_ads(domain)
    results = []
    for line in search_lines:
        parts = [p.strip() for p in line.split(",")]
        found = False
        for ad_line in ads_lines:
            ad_parts = [p.strip() for p in ad_line.split(",")]
            match = True
            for i, part in enumerate(parts):
                if i < len(ad_parts):
                    if case_sensitive.get(i, False):
                        if part != ad_parts[i]:
                            match = False
                            break
                    else:
                        if part.lower() != ad_parts[i].lower():
                            match = False
                            break
                else:
                    match = False
                    break
            if match:
                found = True
                break
        results.append("YES" if found else "NO")
    return [domain] + results

# === RUN CHECK ===
if st.button("Run Check"):
    if not domains or not search_lines:
        st.warning("Please provide both domains and search lines.")
    else:
        start_time = time.time()
        results = []

        progress_bar = st.progress(0)
        total = len(domains)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_domain, d, search_lines): d for d in domains}
            for i, future in enumerate(as_completed(futures)):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append([futures[future]] + ["ERROR"] * len(search_lines))
                progress_bar.progress((i + 1) / total)

        elapsed_time = time.time() - start_time

        # === TABLE PREVIEW ===
        headers = ["Domain"] + search_lines
        df = pd.DataFrame(results, columns=headers)
        st.write("✅ Results Preview:")
        st.dataframe(df)

        # === DOWNLOAD ===
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_buffer.getvalue(),
            file_name=f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

        # === TIME TAKEN ===
        st.success(f"⏱ Time taken: {elapsed_time:.2f} seconds")
