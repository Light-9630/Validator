import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO

# --- Configuration ---
RETRY_ATTEMPTS = 3
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Helper Functions ---

def check_domain(domain, ads_file_type, lines_to_check, case_sensitive):
    """Checks a single domain for the presence of specific lines in its ads.txt/app-ads.txt file."""
    domain_results = {"Page": domain}
    url = f"http://{domain}/{ads_file_type}"
    content = ""
    status_code = ""

    try:
        response = requests.get(url, timeout=10, headers=HEADERS)
        status_code = response.status_code
        
        if response.status_code == 200:
            content = response.text.strip().splitlines()
        else:
            domain_results["Error"] = f"HTTP Error: {status_code}"
            for line_to_check in lines_to_check:
                domain_results[line_to_check] = "No"
            return domain_results

    except requests.exceptions.RequestException as e:
        domain_results["Error"] = f"Request Error: {e}"
        for line_to_check in lines_to_check:
            domain_results[line_to_check] = "No"
        return domain_results

    for line_to_check in lines_to_check:
        found = False
        # Strip whitespace from the searched line
        line_to_check_stripped = line_to_check.strip()
        
        for line_in_content in content:
            line_in_content_stripped = line_in_content.strip()
            if case_sensitive:
                if line_to_check_stripped == line_in_content_stripped:
                    found = True
                    break
            else:
                if line_to_check_stripped.lower() == line_in_content_stripped.lower():
                    found = True
                    break
        domain_results[line_to_check] = "Yes" if found else "No"

    return domain_results

def run_checker(domains, ads_file_type, lines_to_check, case_sensitive_settings):
    """Main function to run the bulk checker with multithreading."""
    results_list = []
    total_domains = len(domains)
    start_time = time.time()
    
    # Create a progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_domain, domain, ads_file_type, lines_to_check, case_sensitive_settings): domain for domain in domains}
        
        for i, future in enumerate(as_completed(futures)):
            domain_result = future.result()
            results_list.append(domain_result)

            # Update progress
            progress = (i + 1) / total_domains
            progress_bar.progress(progress)
            status_text.text(f"Checking domains... {i + 1}/{total_domains}")

    progress_bar.empty()
    status_text.empty()
    end_time = time.time()
    st.success(f"Checks complete! Total time taken: {end_time - start_time:.2f} seconds.")

    return pd.DataFrame(results_list)

# --- Streamlit UI ---

st.set_page_config(layout="wide", page_title="Ads.txt / App-ads.txt Bulk Checker")

st.title("🔥 Ads.txt / App-ads.txt Bulk Checker")
st.write("Paste a list of domains or upload a file, then enter the lines you want to check for.")

# --- File Type Selection ---
ads_file_type = st.radio("Select file type to check:", ("ads.txt", "app-ads.txt"))

# --- Input Area ---
col1, col2 = st.columns(2)

with col1:
    domain_input = st.text_area("Paste Domains (one per line)", height=200)

with col2:
    uploaded_file = st.file_uploader("Upload a CSV/TXT file with domains", type=["txt", "csv"])

# --- Lines Management ---
st.subheader("Lines to Check")
st.write(f"Enter the specific lines you want to find in the `{ads_file_type}` file.")
line_input_key = "line_input"
line_input = st.text_area("Paste Lines (one per line)", height=150, key=line_input_key)

lines_to_check = [line.strip() for line in line_input.splitlines() if line.strip()]

# Create a DataFrame for the editable table
if "lines_df" not in st.session_state or len(lines_to_check) != len(st.session_state.lines_df):
    st.session_state.lines_df = pd.DataFrame(lines_to_check, columns=["Line"])
    st.session_state.lines_df["Case Sensitive"] = False

# Display and edit the table
if not st.session_state.lines_df.empty:
    st.write("Edit and manage the lines to be checked:")
    st.session_state.lines_df = st.data_editor(st.session_state.lines_df, use_container_width=True, num_rows="dynamic")
    
    col_sel1, col_sel2 = st.columns([1, 4])
    with col_sel1:
        if st.checkbox("Select all case-sensitive", value=False):
            st.session_state.lines_df["Case Sensitive"] = True
        else:
            st.session_state.lines_df["Case Sensitive"] = False

else:
    st.info("Please enter or paste lines to check.")

# --- Processing and Output ---
if st.button("Start Checking"):
    
    all_domains = []
    
    # Process pasted domains
    if domain_input:
        all_domains.extend([d.strip().replace("http://", "").replace("https://", "").replace("www.", "") for d in domain_input.splitlines() if d.strip()])
    
    # Process uploaded file
    if uploaded_file:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        file_domains = [line.strip().replace("http://", "").replace("https://", "").replace("www.", "") for line in stringio.readlines() if line.strip()]
        all_domains.extend(file_domains)

    # Remove duplicates
    all_domains = sorted(list(set(all_domains)))
    
    if not all_domains:
        st.error("Please enter or upload at least one domain.")
    else:
        st.subheader("Results")
        lines_df = st.session_state.lines_df
        results_df = run_checker(all_domains, ads_file_type, lines_df["Line"].tolist(), lines_df["Case Sensitive"].tolist())
        
        # Display the results table
        st.dataframe(results_df, use_container_width=True)
        
        # Download button
        csv_export = results_df.to_csv(index=False)
        st.download_button(
            label="Download Results as CSV",
            data=csv_export,
            file_name=f"{ads_file_type.replace('.', '_')}_results.csv",
            mime="text/csv",
        )

st.markdown("---")
st.markdown("Built with Streamlit by a helpful AI assistant.")
<br>

***

Here's an instructional video that shows how to build an interactive ad-scraping web app with Streamlit and Python. [How to build an Interactive Ad-scraping Keyword Analysis Web App with Streamlit Python & ScraperAPI](https://www.youtube.com/watch?v=yb1OF33pNTQ). This video is relevant because it demonstrates building a similar Streamlit application that handles data scraping and analysis, which is conceptually related to the task of checking ads.txt files.
http://googleusercontent.com/youtube_content/0
