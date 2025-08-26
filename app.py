import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re

st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")

st.title("Ads.txt / App-ads.txt Bulk Checker")

# Use columns for better layout
col1, col2 = st.columns(2)

with col1:
    st.header("Input Domains")
    domain_input = st.text_area("Paste domains (one per line)", height=200)
    uploaded_file = st.file_uploader("Or upload CSV/TXT file with domains (one per line)", type=["csv", "txt"])

with col2:
    st.header("Search Lines")
    line_input = st.text_area("Paste search lines (one per line, elements comma-separated)", height=200)

# Process domains
domains = []
if domain_input:
    domains = [d.strip() for d in domain_input.split('\n') if d.strip()]
if uploaded_file is not None:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
    domains.extend(uploaded_domains)
domains = list(set(domains))  # Remove duplicates

if domains:
    st.info(f"{len(domains)} unique domains loaded.")

# Select file type
file_type = st.selectbox("Select file type to check", ["ads.txt", "app-ads.txt"])

# Process lines
lines = [l.strip() for l in line_input.split('\n') if l.strip()]

# Lines management with element-wise case sensitivity
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("Lines Management", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            elements = [e.strip() for e in line.split(',') if e.strip()]
            line_elements[line] = elements
            case_sensitives[line] = {}
            st.markdown(f"**Line: {line}**")
            cols = st.columns(len(elements))
            for i, element in enumerate(elements):
                with cols[i]:
                    case_sensitives[line][element] = st.checkbox(
                        element,
                        value=select_all_case,
                        key=f"case_{line}_{element}"
                    )

# Start checking button
if st.button("Start Checking", disabled=not (domains and lines)):
    start_time = time.time()
    
    # Initialize results dict
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    
    errors = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
    }
    
    def fetch_with_retry(domain, max_retries=3):
        urls = [
            f"https://{domain}/{file_type}",
            f"http://{domain}/{file_type}"
        ]
        error = None
        for url in urls:
            for attempt in range(max_retries):
                try:
                    response = requests.get(
                        url,
                        headers=HEADERS,
                        timeout=10,
                        allow_redirects=True,
                        verify=True
                    )
                    if response.status_code == 200:
                        return response.text, None
                    else:
                        error = f"HTTP {response.status_code}"
                except requests.exceptions.SSLError:
                    try:
                        response = requests.get(
                            url,
                            headers=HEADERS,
                            timeout=10,
                            allow_redirects=True,
                            verify=False
                        )
                        if response.status_code == 200:
                            return response.text, None
                        else:
                            error = f"HTTP {response.status_code}"
                    except Exception as e:
                        error = str(e)
                except Exception as e:
                    error = str(e)
                time.sleep(2 ** attempt)
        return None, error
    
    def check_line_in_content(content, line_elements, case_sensitives_line):
        content_lines = content.split('\n')
        
        # Regex to handle whitespace and comments
        cleaned_content_lines = [
            re.split(r'\s*#', content_line.strip())[0].strip()
            for content_line in content_lines
            if content_line.strip() and not content_line.strip().startswith('#')
        ]

        for cleaned_content_line in cleaned_content_lines:
            content_line_elements = [e.strip() for e in cleaned_content_line.split(',')]
            
            all_elements_match = True
            
            for i, element_to_find in enumerate(line_elements):
                if i >= len(content_line_elements):
                    all_elements_match = False
                    break
                
                content_element = content_line_elements[i]
                
                if case_sensitives_line.get(element_to_find, False):
                    if element_to_find != content_element:
                        all_elements_match = False
                        break
                else:
                    if element_to_find.lower() != content_element.lower():
                        all_elements_match = False
                        break
                        
            if all_elements_match:
                return True
        return False
    
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
                    if domain in domains: # Check if domain still exists in the original list
                         results[line][domains.index(domain)] = "Error"
            else:
                for line in lines:
                    if domain in domains:
                        found = check_line_in_content(content, line_elements[line], case_sensitives[line])
                        results[line][domains.index(domain)] = "Yes" if found else "No"
            
            processed += 1
            progress_bar.progress(processed / len(domains))
            status_text.text(f"Processed {processed}/{len(domains)} domains...")
    
    end_time = time.time()
    st.success(f"Checking complete! Time taken: {end_time - start_time:.2f} seconds")
    
    # Display results table
    st.subheader("Results")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, height=400)
    
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
        st.dataframe(error_df, use_container_width=True)

