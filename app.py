import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re
import random
import cloudscraper

st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("Ads.txt / App-ads.txt Bulk Checker")

# ---------------- Input Columns ----------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Enter Domains")
    domains_input = st.text_area("One domain per line (without https://)", height=200, placeholder="example.com\nanotherdomain.com")

with col2:
    st.subheader("Upload File")
    uploaded_file = st.file_uploader("Upload .txt or .csv file with domains", type=["txt", "csv"])

file_type = st.selectbox("Select file type to check", ["ads.txt", "app-ads.txt"])
ua_choice = st.selectbox("User-Agent Mode", ["Random Desktop", "Random Mobile", "Custom", "Cloudflare Bypass (cloudscraper)"])
custom_ua = ""
if ua_choice == "Custom":
    custom_ua = st.text_input("Enter custom User-Agent")

proxy_input = st.text_area("Optional: Enter proxy (http://user:pass@host:port)", height=70)

# ---------------- Helper Functions ----------------
def build_headers():
    desktop_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]
    mobile_agents = [
        "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    ]
    
    if ua_choice == "Random Desktop":
        ua = random.choice(desktop_agents)
    elif ua_choice == "Random Mobile":
        ua = random.choice(mobile_agents)
    elif ua_choice == "Custom":
        ua = custom_ua
    else:
        ua = random.choice(desktop_agents)  # fallback for cloudscraper

    return {"User-Agent": ua, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}

proxies = None
if proxy_input.strip():
    proxies = {"http": proxy_input.strip(), "https": proxy_input.strip()}

def fetch_with_retry(domain, max_retries=3):
    urls = [f"https://{domain}/{file_type}", f"http://{domain}/{file_type}"]
    error = None
    
    for url in urls:
        for attempt in range(max_retries):
            headers = build_headers()
            try:
                if ua_choice == "Cloudflare Bypass (cloudscraper)":
                    scraper = cloudscraper.create_scraper()
                    response = scraper.get(url, headers=headers, timeout=15, proxies=proxies)
                else:
                    response = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=True, proxies=proxies)

                if response.status_code == 200:
                    return response.text, None
                elif response.status_code == 403:
                    error = f"HTTP 403 Forbidden (blocked by site)"
                else:
                    error = f"HTTP {response.status_code}"
            
            except Exception as e:
                error = str(e)
            
            time.sleep(2 ** attempt)
    
    return None, error

# ---------------- Process Domains ----------------
domains = []
if domains_input:
    domains.extend([d.strip() for d in domains_input.splitlines() if d.strip()])
if uploaded_file:
    if uploaded_file.name.endswith(".txt"):
        domains.extend([line.strip() for line in StringIO(uploaded_file.getvalue().decode("utf-8")).readlines() if line.strip()])
    elif uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        domains.extend(df.iloc[:, 0].dropna().astype(str).tolist())

domains = list(set(domains))  # unique

results = []
if st.button("Check Files"):
    progress = st.progress(0)
    total = len(domains)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_domain = {executor.submit(fetch_with_retry, domain): domain for domain in domains}
        
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            content, error = future.result()
            results.append({"Domain": domain, "Status": "Found" if content else "Error", "Details": error if error else "OK"})
            
            completed += 1
            progress.progress(completed / total)

    df = pd.DataFrame(results)
    st.subheader("Results")
    st.dataframe(df)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Results", csv, "results.csv", "text/csv")
