import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from requests.adapters import HTTPAdapter, Retry
import io

# ================= SETTINGS =================
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === INPUTS ===
col1, col2 = st.columns(2)

with col1:
    st.subheader("Domains List")
    domains_input = st.text_area(
        "Paste domains here (one per line):",
        placeholder="example.com\nanotherdomain.com",
        height=200
    )

with col2:
    st.subheader("Lines to Check")
    lines_input = st.text_area(
        "Paste lines here (domain, id, [relation]):",
        placeholder="pubmatic.com, 166253\nopenx.com, 12345, DIRECT",
        height=200
    )

# Toggle for ads.txt or app-ads.txt
file_type = st.radio("File type to check:", ["ads.txt", "app-ads.txt"], horizontal=True)

# Parse user input
domains = [d.strip() for d in domains_input.splitlines() if d.strip()]
raw_lines = [l.strip() for l in lines_input.splitlines() if l.strip()]

parsed_lines = []
for line in raw_lines:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 2:
        parsed_lines.append(parts[:3])  # keep only first 3 parts max

if parsed_lines:
    st.subheader("Parsed Lines (Editable)")
    df_lines = pd.DataFrame(parsed_lines, columns=["Domain", "ID", "Relation"][:len(max(parsed_lines, key=len))])
    edited_df = st.data_editor(df_lines, num_rows="dynamic", key="lines_editor")
else:
    edited_df = pd.DataFrame()

# === FETCH AND CHECK ===
def fetch_file(domain, file_type):
    url = f"https://{domain}/{file_type}"
    try:
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        r = session.get(url, timeout=5)
        if r.status_code == 200:
            return r.text.splitlines()
    except:
        return []
    return []

def check_line_in_file(line_parts, file_lines):
    domain, pub_id = line_parts[0], line_parts[1]
    relation = line_parts[2] if len(line_parts) > 2 else None

    for row in file_lines:
        row_parts = [p.strip() for p in row.split(",")]
        if len(row_parts) < 2:
            continue
        if row_parts[0] == domain and row_parts[1] == pub_id:
            if relation:
                if len(row_parts) >= 3 and row_parts[2].upper() == relation.upper():
                    return "YES"
            else:
                return "YES"
    return "NO"

if st.button("Run Checker 🚀"):
    if not domains or edited_df.empty:
        st.error("Please paste both domains and lines before running.")
    else:
        results = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_domain = {executor.submit(fetch_file, d, file_type): d for d in domains}
            for future in as_completed(future_to_domain):
                domain = future_to_domain[future]
                file_lines = future.result()
                for _, row in edited_df.iterrows():
                    line_parts = [str(x) for x in row if pd.notna(x)]
                    status = check_line_in_file(line_parts, file_lines)
                    results.append({"Check Domain": domain,
                                    "File": file_type,
                                    "Target SSP": line_parts[0],
                                    "Pub ID": line_parts[1],
                                    "Relation": line_parts[2] if len(line_parts) > 2 else "",
                                    "Match": status})

        df_results = pd.DataFrame(results)
        st.success("✅ Checking completed!")

        # Show results
        st.dataframe(df_results)

        # Download CSV
        output_filename = f"ads_check_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_buffer = io.StringIO()
        df_results.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_buffer.getvalue(),
            file_name=output_filename,
            mime="text/csv"
        )
