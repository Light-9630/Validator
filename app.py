import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re

st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("Ads.txt / App-ads.txt Bulk Checker")

# ---------------- Input Columns ----------------
col1, col2 = st.columns(2)

with col1:
    urls_input = st.text_area(
        "Enter domains (one per line)", 
        placeholder="example.com\nnews.com\nsite.org"
    )

with col2:
    file_upload = st.file_uploader("Or upload a file with domains", type=["txt", "csv"])

# ---------------- Sidebar Options ----------------
st.sidebar.header("Settings")

# Proxy option
proxy_input = st.sidebar.text_input(
    "Proxy (optional)", 
    placeholder="http://user:pass@host:port OR http://host:port"
)

# UA option
ua_choice = st.sidebar.radio(
    "User-Agent Mode",
    ["Live Browser UA", "AdsBot-Google UA"],
    index=0
)

# Set UA
if ua_choice == "Live Browser UA":
    try:
        import fake_useragent
        ua = fake_useragent.UserAgent().chrome
    except:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
else:
    ua = "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"

headers = {
    "User-Agent": ua,
    "Accept": "text/plain, */*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

# Proxy dict
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None

# ---------------- Process Input ----------------
domains = []

if urls_input:
    domains += [d.strip() for d in urls_input.splitlines() if d.strip()]

if file_upload:
    content = file_upload.read().decode("utf-8")
    if file_upload.name.endswith(".csv"):
        df = pd.read_csv(StringIO(content))
        domains += df.iloc[:, 0].dropna().astype(str).tolist()
    else:
        domains += [d.strip() for d in content.splitlines() if d.strip()]

domains = list(set(domains))  # unique

# ---------------- Fetch Function ----------------
def fetch_ads_txt(domain):
    urls_to_try = [
        f"https://{domain}/ads.txt",
        f"http://{domain}/ads.txt",
        f"https://{domain}/app-ads.txt",
        f"http://{domain}/app-ads.txt",
    ]

    for url in urls_to_try:
        try:
            r = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            if r.status_code == 200 and "google.com" in r.text.lower():
                return domain, url, "FOUND", r.status_code
            elif r.status_code == 200:
                return domain, url, "OK (No Google)", r.status_code
            elif r.status_code in [403, 404]:
                return domain, url, "ERROR", r.status_code
        except Exception as e:
            return domain, url, f"Failed ({str(e)})", None

    return domain, None, "Not Found", None

# ---------------- Run Bulk Check ----------------
if st.button("Check Ads.txt / App-ads.txt"):
    start = time.time()
    results = []

    with st.spinner("Checking domains..."):
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_ads_txt, d): d for d in domains}
            for future in as_completed(futures):
                results.append(future.result())

    df = pd.DataFrame(results, columns=["Domain", "URL Tried", "Status", "HTTP Code"])

    st.success(f"Done in {time.time()-start:.2f}s")
    st.dataframe(df, use_container_width=True)

    # Download option
    csv = df.to_csv(index=False)
    st.download_button("Download Results CSV", csv, "results.csv", "text/csv")
