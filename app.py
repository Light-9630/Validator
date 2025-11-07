import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- Page Setup ----------------
st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("🔎 Ads.txt / App-ads.txt Bulk Checker")

# ---------------- Input Tabs ----------------
tab1, tab2 = st.tabs(["📋 Paste Domains", "📂 Upload Domains File"])

domains = []
with tab1:
    st.header("Input Domains")
    domain_input = st.text_area("Paste domains (one per line)", height=200)
    if domain_input:
        domains = [d.strip() for d in domain_input.splitlines() if d.strip()]

with tab2:
    st.header("Upload File")
    uploaded_file = st.file_uploader("Upload CSV/TXT file with domains", type=["csv", "txt"])
    if uploaded_file:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
        domains.extend(uploaded_domains)

# Deduplicate but preserve order
domains = list(dict.fromkeys(domains))
if domains:
    st.info(f"✅ {len(domains)} unique domains loaded.")

# ---------------- Search Lines ----------------
st.header("🔍 Search Lines")
line_input = st.text_area("Paste search lines (CSV format or single word/number, one per line)", height=200)

# ---------------- File type selection ----------------
file_type = st.selectbox("Select file type", ["ads.txt", "app-ads.txt"])

# ---------------- Field Limit Selection ----------------
field_limit = st.selectbox(
    "Select number of fields to check",
    [1, 2, 3, 4],
    index=1
)

# ---------------- Process Lines ----------------
lines = [l.strip() for l in line_input.splitlines() if l.strip()]
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("⚙ Line Settings", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            if "," in line:
                elements = [e.strip() for e in line.split(',') if e.strip()]
            else:
                elements = [line]
            line_elements[line] = elements[:field_limit]
            case_sensitives[line] = {}
            st.markdown(f"**Line: {line}**")
            cols = st.columns(len(line_elements[line]))
            for i, element in enumerate(line_elements[line]):
                with cols[i]:
                    case_sensitives[line][element] = st.checkbox(
                        element,
                        value=select_all_case,
                        key=f"case_{line}_{element}"
                    )

# ---------------- Sidebar: Proxy + UA Mode ----------------
st.sidebar.header("⚡ Settings")

proxy_input = st.sidebar.text_input(
    "Proxy (optional)",
    placeholder="http://user:pass@host:port OR http://host:port"
)
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None

ua_choice = st.sidebar.radio(
    "User-Agent Mode",
    ["Live Browser UA", "AdsBot-Google UA"],
    index=0
)

if ua_choice == "Live Browser UA":
    LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
else:
    LIVE_UA = "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"

st.sidebar.write(f"🟢 Using User-Agent: {LIVE_UA}")

# ---------------- Global Session + Retry Added ----------------
session = requests.Session()
session.headers.update({
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,/;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': LIVE_UA
})
if proxies:
    session.proxies.update(proxies)

retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ---------------- Fetch with Retry (timeout increased to 20) ----------------
def fetch_with_retry(domain, max_retries=2, timeout=20):
    urls = [f"https://{domain}/{file_type}", f"http://{domain}/{file_type}"]
    last_error = None
    for url in urls:
        for attempt in range(max_retries):
            try:
                response = session.get(url, timeout=timeout, allow_redirects=True)
                if response.status_code == 200:
                    return response.text, None
                else:
                    last_error = f"HTTP {response.status_code}"
            except requests.exceptions.SSLError:
                try:
                    response = session.get(url, timeout=timeout, allow_redirects=True, verify=False)
                    if response.status_code == 200:
                        return response.text, None
                    else:
                        last_error = f"HTTP {response.status_code}"
                except Exception as e:
                    last_error = str(e)
            except Exception as e:
                last_error = str(e)
    return None, last_error

# ---------------- Check line content ----------------
def check_line_in_content(content, line_elements, case_sensitives_line):
    content_lines = content.splitlines()
    cleaned_lines = [
        re.split(r'\s*#', line.strip())[0].strip()
        for line in content_lines
        if line.strip() and not line.strip().startswith('#')
    ]
    
    for c_line in cleaned_lines:
        content_parts = [e.strip() for e in c_line.split(',')]

        if len(line_elements) == 1 and "," not in line_elements[0]:
            element_to_find = line_elements[0]
            if case_sensitives_line.get(element_to_find, False):
                if element_to_find in c_line:
                    return True
            else:
                if element_to_find.lower() in c_line.lower():
                    return True
        else:
            all_match = True
            for i, element_to_find in enumerate(line_elements):
                if i >= len(content_parts):
                    all_match = False
                    break
                content_element = content_parts[i]
                if case_sensitives_line.get(element_to_find, False):
                    if element_to_find != content_element:
                        all_match = False
                        break
                else:
                    if element_to_find.lower() != content_element.lower():
                        all_match = False
                        break
            if all_match:
                return True
    return False

# ---------------- Main Checking ----------------
if st.button("🚀 Start Checking", disabled=not (domains and lines)):
    start_time = time.time()
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    errors = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_index = {executor.submit(fetch_with_retry, domain): idx for idx, domain in enumerate(domains)}
        for processed, future in enumerate(as_completed(future_to_index), 1):
            idx = future_to_index[future]
            domain = domains[idx]
            try:
                content, err = future.result()
            except Exception as e:
                content, err = None, str(e)
            if err:
                errors[domain] = err
                for line in lines:
                    results[line][idx] = "Error"
            else:
                for line in lines:
                    found = check_line_in_content(content, line_elements[line], case_sensitives[line])
                    results[line][idx] = "Yes" if found else "No"
            progress_bar.progress(processed / len(domains))
            status_text.text(f"Processed {processed}/{len(domains)} domains...")
    
    end_time = time.time()
    st.success(f"🎉 Checking complete! Time taken: {end_time - start_time:.2f} seconds")
    
    st.subheader("📊 Results")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, height=400)
    
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button("💾 Download Results as CSV", data=csv_data, file_name="ads_txt_check_results.csv", mime="text/csv")
    
    if errors:
        st.subheader("Errors")
        error_df = pd.DataFrame({"Page": list(errors.keys()), "Error": list(errors.values())})
        st.dataframe(error_df, use_container_width=True)
