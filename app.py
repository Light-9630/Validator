import streamlit as st
import pandas as pd
from datetime import datetime

# ==== PAGE CONFIG ====
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Checker")

# ==== HELPER FUNCTIONS ====
def normalize(val):
    """Remove spaces, commas, lowercase"""
    return val.replace(" ", "").replace(",", "").lower()

def parse_line(line):
    """Split line into exactly 3 parts: Domain, Seller ID, Type"""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        parts += [""] * (3 - len(parts))  # pad missing
    return parts[:3]  # keep only first 3

def get_lines_from_input(text):
    return [line.strip() for line in text.strip().splitlines() if line.strip()]

def match_lines(source_lines, check_lines):
    """Compare with seller ID case-sensitive"""
    source_parsed = [parse_line(line) for line in source_lines]
    matches, mismatches = [], []

    for check_line in check_lines:
        check_parts = parse_line(check_line)
        found = False
        for src_parts in source_parsed:
            # Field 1 & 3 → ignore case/spaces/commas
            cond1 = normalize(src_parts[0]) == normalize(check_parts[0])
            cond3 = normalize(src_parts[2]) == normalize(check_parts[2])
            # Seller ID (index 1) → exact match (case-sensitive)
            cond2 = src_parts[1] == check_parts[1]

            if cond1 and cond2 and cond3:
                matches.append(check_parts)
                found = True
                break
        if not found:
            mismatches.append(check_parts)

    return matches, mismatches

# ==== MODE SELECTION ====
mode = st.radio("Select File Type", ["ads.txt", "app-ads.txt"])
st.write(f"**Mode Selected:** {mode}")

# ==== INPUT OPTIONS ====
input_type = st.radio("Select Input Method", ["Paste Text", "Upload File"])

if input_type == "Paste Text":
    st.subheader("Source List")
    source_text = st.text_area("Paste Source (Reference) List Here", height=200)
    st.subheader("Check List")
    check_text = st.text_area("Paste Check List Here", height=200)

elif input_type == "Upload File":
    st.subheader("Source List")
    source_file = st.file_uploader("Upload Source (Reference) File", type=["txt", "csv"])
    st.subheader("Check List")
    check_file = st.file_uploader("Upload Check File", type=["txt", "csv"])

# ==== PROCESS ====
if st.button("🔍 Compare"):
    if input_type == "Paste Text":
        if not source_text or not check_text:
            st.error("Please paste both source and check lists.")
        else:
            source_lines = get_lines_from_input(source_text)
            check_lines = get_lines_from_input(check_text)
            matches, mismatches = match_lines(source_lines, check_lines)

    elif input_type == "Upload File":
        if not source_file or not check_file:
            st.error("Please upload both source and check files.")
        else:
            source_content = source_file.read().decode("utf-8")
            check_content = check_file.read().decode("utf-8")
            source_lines = get_lines_from_input(source_content)
            check_lines = get_lines_from_input(check_content)
            matches, mismatches = match_lines(source_lines, check_lines)

    if 'matches' in locals():
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        matches_df = pd.DataFrame(matches, columns=["Domain", "Seller ID", "Type"])
        matches_df["Match Status"] = "YES"

        mismatches_df = pd.DataFrame(mismatches, columns=["Domain", "Seller ID", "Type"])
        mismatches_df["Match Status"] = "NO"

        full_df = pd.concat([matches_df, mismatches_df], ignore_index=True)

        st.dataframe(full_df)

        csv_bytes = full_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ Download Results CSV",
            csv_bytes,
            f"{mode}_comparison_{now_str}.csv",
            "text/csv"
        )
