import streamlit as st
import pandas as pd
import requests
import cloudscraper
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re

st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("Ads.txt / App-ads.txt Bulk Checker")

# ---------------- Input Columns ----------------
col1, col2 = st.columns(2)

with col1:
    st.header("Input Domains")
    domain_input = st.text_area("Paste domains (one per line)", height=200)
    uploaded_file = st.file_uploader("Or upload CSV/TXT file with domains", type=["csv","txt"])

with col2:
    st.header("Search Lines")
    line_input = st.text_area("Paste search lines (one per line, CSV format)", height=200)

# ---------------- Process Domains ----------------
domains = []
if domain_input:
    domains = [d.strip() for d in domain_input.splitlines() if d.strip()]
if uploaded_file:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
    domains.extend(uploaded_domains)
domains = list(set(domains))
if domains:
    st.info(f"{len(domains)} unique domains loaded.")

# ---------------- File type selection ----------------
file_type = st.selectbox(
    "Select file type / Mode",
    ["ads.txt", "app-ads.txt", "Custom Text Search"]
)

# ---------------- Field Limit Selection ----------------
field_limit = st.selectbox(
    "Select number of fields to check",
    [1, 2, 3, 4],
    index=1  # default = 2
)

# ---------------- Process Lines ----------------
lines = [l.strip() for l in line_input.splitlines() if l.strip()]
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("Lines Management", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            elements = [e.strip() for e in line.split(',') if e.strip()]
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
st.sidebar.header("Settings")

proxy_input = st.sidebar.text_input(
    "Proxy (optional)",
    placeholder="http://user:pass@host:port OR http://host:port"
)
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None

ua_choice = st.sidebar.radio(
    "User-Agent Mode",
    ["Live Browser UA", "AdsBot-Google UA", "Cloudflare Bypass (cloudscraper)"],
    index=0
)

# ---------------- Fetch Live UA ----------------
def get_live_ua():
    try:
        r = requests.get("https://httpbin.org/user-agent", timeout=5)
        return r.json()["user-agent"]
    except:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"

if ua_choice == "Live Browser UA":
    LIVE_UA = get_live_ua()
elif ua_choice == "AdsBot-Google UA":
    LIVE_UA = "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"
else:
    LIVE_UA = None  # cloudscraper will handle UA itself

if LIVE_UA:
    st.sidebar.write(f"Using User-Agent: {LIVE_UA}")
else:
    st.sidebar.write("Using Cloudflare Bypass Mode (cloudscraper)")

# ---------------- Common headers ----------------
def build_headers():
    if LIVE_UA:
        return {
            "User-Agent": LIVE_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
    else:
        return {}

# ---------------- Fetch with retry, redirects & SSL fallback ----------------
def fetch_with_retry(domain, max_retries=3):
    if file_type == "Custom Text Search":
        urls = [f"https://{domain}", f"http://{domain}"]  # root page
    else:
        urls = [f"https://{domain}/{file_type}", f"http://{domain}/{file_type}"]

    error = None
    session = cloudscraper.create_scraper() if ua_choice == "Cloudflare Bypass (cloudscraper)" else requests

    for url in urls:
        for attempt in range(max_retries):
            headers = build_headers()
            try:
                response = session.get(url, headers=headers, timeout=10, allow_redirects=True, verify=True, proxies=proxies)
                if response.status_code == 200:
                    return response.text, None
                elif response.status_code == 403:
                    return None, f"HTTP {response.status_code} (Forbidden)"
                else:
                    error = f"HTTP {response.status_code}"
            except requests.exceptions.SSLError:
                try:
                    response = session.get(url, headers=headers, timeout=10, allow_redirects=True, verify=False, proxies=proxies)
                    if response.status_code == 200:
                        return response.text, None
                    elif response.status_code == 403:
                        return None, f"HTTP {response.status_code} (Forbidden)"
                    else:
                        error = f"HTTP {response.status_code}"
                except Exception as e:
                    error = str(e)
            except Exception as e:
                error = str(e)
            time.sleep(2 ** attempt)
    return None, error

# ---------------- Check line content ----------------
def check_line_in_content(content, line_elements, case_sensitives_line):
    if file_type == "Custom Text Search":
        # search entire HTML/text body
        for element_to_find in line_elements:
            found = False
            if case_sensitives_line.get(element_to_find, False):
                if element_to_find in content:
                    found = True
            else:
                if element_to_find.lower() in content.lower():
                    found = True
            if not found:
                return False
        return True
    else:
        # ads.txt style line-by-line check
        content_lines = content.splitlines()
        cleaned_lines = [
            re.split(r'\s*#', line.strip())[0].strip()
            for line in content_lines
            if line.strip() and not line.strip().startswith('#')
        ]
        for c_line in cleaned_lines:
            content_parts = [e.strip() for e in c_line.split(',')]
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
if st.button("Start Checking", disabled=not (domains and lines)):
    start_time = time.time()
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    errors = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_domain = {executor.submit(fetch_with_retry, domain): domain for domain in domains}
        processed = 0
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                content, err = future.result()
            except Exception as e:
                content, err = None, str(e)
            if err:
                errors[domain] = err
                for line in lines:
                    results[line][domains.index(domain)] = "Error"
            else:
                for line in lines:
                    found = check_line_in_content(content, line_elements[line], case_sensitives[line])
                    results[line][domains.index(domain)] = "Yes" if found else "No"
            processed += 1
            progress_bar.progress(processed / len(domains))
            status_text.text(f"Processed {processed}/{len(domains)} domains...")
    
    end_time = time.time()
    st.success(f"Checking complete! Time taken: {end_time - start_time:.2f} seconds")
    
    # --- Display results ---
    st.subheader("Results")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, height=400)
    
    # --- Download CSV ---
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Results as CSV", data=csv_data, file_name="ads_txt_check_results.csv", mime="text/csv")
    
    # --- Display Errors ---
    if errors:
        st.subheader("Errors")
        error_df = pd.DataFrame({"Page": list(errors.keys()), "Error": list(errors.values())})
        st.dataframe(error_df, use_container_width=True)
