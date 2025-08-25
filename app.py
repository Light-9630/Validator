import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import json

# Note: The sellers.json is provided in the query, but since it's truncated, this code assumes a general tool.
# If needed, you can parse and auto-populate lines from a JSON string here.
# For example:
# sellers_json = '''{the json string}'''
# data = json.loads(sellers_json)
# Then generate lines like [f"{seller['domain']}, {seller['seller_id']}, {'DIRECT' if seller['seller_type'] == 'PUBLISHER' else 'RESELLER'}" for seller in data['sellers']]
# But as per requirements, lines are user-input.

st.title("🔥 Ads.txt / App-ads.txt Bulk Checker")

# Select file type
file_type = st.selectbox("Select file type to check", ["ads.txt", "app-ads.txt"])

# Input for domains
st.header("Input Domains")
domain_input = st.text_area("Paste domains (one per line)", height=150)
uploaded_file = st.file_uploader("Or upload CSV/TXT file with domains (one per line)", type=["csv", "txt"])

domains = []
if domain_input:
    domains = [d.strip() for d in domain_input.split('\n') if d.strip()]
if uploaded_file is not None:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
    domains.extend(uploaded_domains)
domains = list(set(domains))  # Remove duplicates

if domains:
    st.write(f"{len(domains)} unique domains loaded.")

# Input for search lines
st.header("Search Lines")
line_input = st.text_area("Paste search lines (one per line)", height=150)
lines = [l.strip() for l in line_input.split('\n') if l.strip()]

# Lines management
case_sensitives = {}
if lines:
    st.subheader("Lines Management")
    select_all_case = st.checkbox("Select all as case-sensitive")
    for line in lines:
        case_sensitives[line] = st.checkbox(f"Case-sensitive for: {line}", value=select_all_case, key=f"case_{line}")
    st.write(" ")  # Spacer

# Start checking button
if st.button("Start Checking") and domains and lines:
    start_time = time.time()
    
    # Initialize results dict
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    
    errors = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def fetch_with_retry(domain, max_retries=3):
        url = f"https://{domain}/{file_type}"
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response.text, None
                else:
                    error = f"HTTP {response.status_code}"
            except Exception as e:
                error = str(e)
            time.sleep(2 ** attempt)  # Exponential backoff
        return None, error
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_domain = {executor.submit(fetch_with_retry, domain): domain for domain in domains}
        processed = 0
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            content, err = future.result()
            if err:
                errors[domain] = err
                for line in lines:
                    results[line][domains.index(domain)] = "Error"
            else:
                for line in lines:
                    if case_sensitives[line]:
                        found = line in content
                    else:
                        found = line.lower() in content.lower()
                    results[line][domains.index(domain)] = "Yes" if found else "No"
            
            processed += 1
            progress_bar.progress(processed / len(domains))
            status_text.text(f"Processed {processed}/{len(domains)} domains...")
    
    end_time = time.time()
    st.success(f"Checking complete! Time taken: {end_time - start_time:.2f} seconds")
    
    # Display results table
    st.subheader("Results")
    df = pd.DataFrame(results)
    st.table(df)
    
    # Download button
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Results as CSV",
        data=csv_data,
        file_name="ads_txt_check_results.csv",
        mime="text/csv"
    )
    
    # Errors if any
    if errors:
        st.subheader("Errors")
        error_df = pd.DataFrame({"Page": list(errors.keys()), "Error": list(errors.values())})
        st.table(error_df)
