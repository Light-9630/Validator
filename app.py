import streamlit as st
import pandas as pd
import re
import time

st.set_page_config(page_title="ads.txt Line Checker", layout="wide")

# ---------------- Helper Function ----------------
def check_line_in_content(content, line_elements, case_sensitives_line):
    content_lines = content.splitlines()
    cleaned_lines = [
        re.split(r'\s*#', line.strip())[0].strip()
        for line in content_lines
        if line.strip() and not line.strip().startswith('#')
    ]
    for c_line in cleaned_lines:
        content_parts = [e.strip() for e in c_line.split(',')]
        if len(content_parts) < len(line_elements):
            continue
        all_match = True
        for i, element_to_find in enumerate(line_elements):
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

# ---------------- UI ----------------
st.title("🔍 Ads.txt Line Checker")

# Field selection
st.subheader("Search Settings")
field_limit = st.selectbox(
    "Select how many fields to check",
    options=[2, 3, 4],
    index=0,  # default 2
    help="By default checks Domain + Seller ID (2 fields). You can extend to Type (3) or Cert Authority ID (4)."
)

# Input lines
line_input = st.text_area("Enter lines to search (one per line, comma-separated):")

# Upload / paste domains
st.subheader("Domains Input")
domain_file = st.file_uploader("Upload a file with domains (one per line):", type=["txt", "csv"])
domain_text = st.text_area("Or paste domains here (one per line):")

# ---------------- Process Lines ----------------
lines = [l.strip() for l in line_input.splitlines() if l.strip()]
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("Lines Management", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            elements = [e.strip() for e in line.split(',') if e.strip()]
            # ✅ Limit fields dynamically
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

# ---------------- Domains ----------------
domains = []
if domain_file:
    if domain_file.name.endswith("csv"):
        df = pd.read_csv(domain_file, header=None)
        domains = df[0].astype(str).tolist()
    else:
        domains = domain_file.read().decode("utf-8").splitlines()

if domain_text:
    domains += [d.strip() for d in domain_text.splitlines() if d.strip()]

domains = list(set(domains))  # remove duplicates

# ---------------- Run Check ----------------
if st.button("Run Check"):
    if not lines:
        st.error("Please enter at least one line to search.")
    elif not domains:
        st.error("Please upload or paste at least one domain.")
    else:
        results = []
        start_time = time.time()
        progress = st.progress(0)
        status_text = st.empty()

        for i, domain in enumerate(domains):
            try:
                import requests
                url = f"http://{domain}/ads.txt"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    content = resp.text
                    for line in lines:
                        found = check_line_in_content(content, line_elements[line], case_sensitives[line])
                        results.append({"Domain": domain, "Line": line, "Found": "Yes" if found else "No"})
                else:
                    for line in lines:
                        results.append({"Domain": domain, "Line": line, "Found": f"Error {resp.status_code}"})
            except Exception as e:
                for line in lines:
                    results.append({"Domain": domain, "Line": line, "Found": f"Error: {e}"})

            progress.progress((i + 1) / len(domains))
            status_text.text(f"Processed {i+1}/{len(domains)} domains...")

        elapsed = time.time() - start_time
        status_text.text(f"Completed in {elapsed:.2f} seconds ✅")

        if results:
            df = pd.DataFrame(results)
            st.dataframe(df)

            # Download option
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download results as CSV",
                data=csv,
                file_name="ads_check_results.csv",
                mime="text/csv",
            )
