import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO

# --- Configuration ---
# You can change this to app-ads.txt if you want to check for app-ads.txt
ADS_TXT_PATH = "ads.txt"
RETRY_ATTEMPTS = 3

# --- Helper Functions ---

def check_domain(domain, lines_to_check, case_sensitive):
    """Checks a single domain for the presence of specific lines in its ads.txt file."""
    domain_results = {"Page": domain}
    url = f"http://{domain}/{ADS_TXT_PATH}"
    content = ""
    status_code = ""

    try:
        response = requests.get(url, timeout=10)
        status_code = response.status_code
        if response.status_code == 200:
            content = response.text.strip().splitlines()
        else:
            domain_results["Error"] = f"HTTP Error: {status_code}"
            for line_to_check in lines_to_check:
                domain_results[line_to_check] = "No" # Or "N/A"
            return domain_results

    except requests.exceptions.RequestException as e:
        domain_results["Error"] = f"Request Error: {e}"
        for line_to_check in lines_to_check:
            domain_results[line_to_check] = "No" # Or "N/A"
        return domain_results

    for line_to_check in lines_to_check:
        found = False
        for line_in_content in content:
            if case_sensitive:
                if line_to_check == line_in_content.strip():
                    found = True
                    break
            else:
                if line_to_check.lower() == line_in_content.strip().lower():
                    found = True
                    break
        domain_results[line_to_check] = "Yes" if found else "No"

    return domain_results

def run_checker(domains, lines_to_check, case_sensitive_settings):
    """Main function to run the bulk checker with multithreading."""
    results_list = []
    total_domains = len(domains)
    start_time = time.time()
    
    # Create a progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_domain, domain, lines_to_check, case_sensitive_settings): domain for domain in domains}
        
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

# --- Input Area ---
col1, col2 = st.columns(2)

with col1:
    domain_input = st.text_area("Paste Domains (one per line)", height=200)

with col2:
    uploaded_file = st.file_uploader("Upload a CSV/TXT file with domains", type=["txt", "csv"])

# --- Lines Management ---
st.subheader("Lines to Check")
st.write("Enter the specific lines you want to find in the `ads.txt` or `app-ads.txt` file.")
line_input_key = "line_input"
line_input = st.text_area("Paste Lines (one per line)", height=150, key=line_input_key)

lines_to_check = [line.strip() for line in line_input.splitlines() if line.strip()]

# Create a DataFrame for the editable table
if "lines_df" not in st.session_state:
    st.session_state.lines_df = pd.DataFrame(lines_to_check, columns=["Line"])
    st.session_state.lines_df["Case Sensitive"] = False

if lines_to_check and len(lines_to_check) != len(st.session_state.lines_df):
    st.session_state.lines_df = pd.DataFrame(lines_to_check, columns=["Line"])
    st.session_state.lines_df["Case Sensitive"] = False

# Display and edit the table
if not st.session_state.lines_df.empty:
    st.session_state.lines_df = st.data_editor(st.session_state.lines_df, use_container_width=True, num_rows="dynamic")
    
    col_sel1, col_sel2 = st.columns([1, 4])
    with col_sel1:
        select_all_case_sensitive = st.checkbox("Select all case-sensitive", value=False)
        if select_all_case_sensitive:
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
        results_df = run_checker(all_domains, lines_df["Line"].tolist(), lines_df["Case Sensitive"].tolist())
        
        # Display the results table
        st.dataframe(results_df, use_container_width=True)
        
        # Download button
        csv_export = results_df.to_csv(index=False)
        st.download_button(
            label="Download Results as CSV",
            data=csv_export,
            file_name="ads_txt_results.csv",
            mime="text/csv",
        )

st.markdown("---")
st.markdown("Built with Streamlit by a helpful AI assistant.")
