import streamlit as st
import pandas as pd
from datetime import datetime

# ==== PAGE CONFIG ====
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Checker")

# ==== HELPERS ====
def normalize(val):
    """Remove spaces, commas, lowercase"""
    return val.replace(" ", "").replace(",", "").lower()

def parse_line(line):
    """Split line into exactly 3 parts for comparison"""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        parts += [""] * (3 - len(parts))
    return parts[:3], line.strip()

def get_lines_from_input(text):
    return [line.strip() for line in text.strip().splitlines() if line.strip()]

def check_matches(source_lines, check_lines):
    """Return dict {check_line: YES/NO}"""
    source_parsed = [parse_line(line) for line in source_lines]
    results = {}

    for check_line in check_lines:
        check_parts, _ = parse_line(check_line)
        matched = False
        for src_parts, _ in source_parsed:
            cond1 = normalize(src_parts[0]) == normalize(check_parts[0])
            cond3 = normalize(src_parts[2]) == normalize(check_parts[2])
            cond2 = src_parts[1] == check_parts[1]  # case-sensitive seller ID
            if cond1 and cond2 and cond3:
                matched = True
                break
        results[check_line] = "YES" if matched else "NO"

    return results

# ==== INPUT OPTIONS ====
input_type = st.radio("Select Input Method", ["Paste Text", "Upload File"])
st.subheader("Check List (lines to search in each domain)")
check_text = st.text_area("Paste Check List Here", height=150)

pages_data = {}  # {page_name: source_lines}

if input_type == "Paste Text":
    num_pages = st.number_input("How many pages/domains?", min_value=1, value=1, step=1)
    for i in range(num_pages):
        page_name = st.text_input(f"Page {i+1} Name (example.com/ads.txt)", key=f"page{i}")
        page_content = st.text_area(f"Paste {page_name or 'Page '+str(i+1)} content here", height=150, key=f"content{i}")
        if page_name and page_content:
            pages_data[page_name] = get_lines_from_input(page_content)

elif input_type == "Upload File":
    uploaded_files = st.file_uploader("Upload one or more source files", type=["txt", "csv"], accept_multiple_files=True)
    for file in uploaded_files:
        page_name = file.name
        page_content = file.read().decode("utf-8")
        pages_data[page_name] = get_lines_from_input(page_content)

# ==== PROCESS ====
if st.button("🔍 Compare"):
    if not check_text:
        st.error("Please paste the check list.")
    elif not pages_data:
        st.error("Please provide at least one page/domain content.")
    else:
        check_lines = get_lines_from_input(check_text)
        final_results = {}

        for page, src_lines in pages_data.items():
            final_results[page] = check_matches(src_lines, check_lines)

        # Create DataFrame: Pages as rows, check_lines as columns
        df = pd.DataFrame.from_dict(final_results, orient="index")
        df = df[check_lines]  # preserve original check line order
        df.index.name = "Page"

        st.dataframe(df)

        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        csv_bytes = df.to_csv().encode("utf-8")
        st.download_button(
            "⬇ Download Results CSV",
            csv_bytes,
            f"comparison_matrix_{now_str}.csv",
            "text/csv"
        )
