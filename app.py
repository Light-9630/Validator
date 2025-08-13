import streamlit as st
import pandas as pd
from datetime import datetime

# ==== PAGE CONFIG ====
st.set_page_config(page_title="ads.txt / app-ads.txt — Single Check", layout="wide")
st.title("📄 Single-Line Check for ads.txt / app-ads.txt")

# ==== HELPERS ====
def normalize(val: str) -> str:
    """Remove spaces and commas, lowercase (for non-seller fields)."""
    return val.replace(" ", "").replace(",", "").lower()

def parse_three_fields(line: str):
    """
    Split into exactly 3 fields (Domain/Exchange, Seller ID, Relationship Type).
    Ignore everything after 3rd field, pad missing as empty.
    """
    # strip comments (# ... ) if present
    line_ = line.split("#", 1)[0].strip()
    if not line_:
        return ["", "", ""], ""
    parts = [p.strip() for p in line_.split(",")]
    if len(parts) < 3:
        parts += [""] * (3 - len(parts))
    return parts[:3], line_.strip()

def first_nonempty_line(text: str) -> str:
    for raw in text.splitlines():
        s = raw.split("#", 1)[0].strip()
        if s:
            return s
    return ""

def get_lines_from_text(text: str):
    """All non-empty, non-comment lines (for domain content)."""
    out = []
    for raw in text.splitlines():
        s = raw.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out

def check_match(domain_lines: list[str], target_line: str) -> bool:
    """True if any line in domain matches the target per rules."""
    tgt_parts, _ = parse_three_fields(target_line)
    if tgt_parts == ["", "", ""]:
        return False

    for src in domain_lines:
        src_parts, _ = parse_three_fields(src)
        if src_parts == ["", "", ""]:
            continue

        # Field 0 (exchange/domain) and Field 2 (relationship) -> normalized compare
        cond1 = normalize(src_parts[0]) == normalize(tgt_parts[0])
        cond3 = normalize(src_parts[2]) == normalize(tgt_parts[2])
        # Field 1 (seller id) -> case-sensitive exact
        cond2 = src_parts[1] == tgt_parts[1]

        if cond1 and cond2 and cond3:
            return True
    return False

# ==== UI ====
st.markdown("**Choose how to provide the domain’s ads.txt/app-ads.txt and the single line to check.**")

with st.expander("Domain/Page Content (choose ONE method)"):
    domain_method = st.radio("Domain content input", ["Paste", "Upload"], horizontal=True, key="dom_m")
    domain_page_name = st.text_input("Page (e.g., example.com/ads.txt or example.com/app-ads.txt)",
                                     placeholder="example.com/app-ads.txt")
    domain_text = ""
    if domain_method == "Paste":
        domain_text = st.text_area("Paste domain file content here", height=200, key="dom_paste")
    else:
        dom_file = st.file_uploader("Upload ads.txt / app-ads.txt", type=["txt", "csv"], key="dom_upload")
        if dom_file:
            domain_text = dom_file.read().decode("utf-8", errors="ignore")
            if not domain_page_name:
                domain_page_name = dom_file.name

with st.expander("Single Line to Search (choose ONE method)", expanded=True):
    line_method = st.radio("Search line input", ["Paste", "Upload"], horizontal=True, key="line_m")
    target_line = ""
    if line_method == "Paste":
        target_line = st.text_input(
            "Paste ONE ads.txt/app-ads.txt line (e.g., google.com, pub-2749054827332983, RESELLER)",
            key="line_paste"
        )
    else:
        line_file = st.file_uploader("Upload a file containing ONE line (uses first non-empty line)",
                                     type=["txt", "csv"], key="line_upload")
        if line_file:
            raw = line_file.read().decode("utf-8", errors="ignore")
            target_line = first_nonempty_line(raw)

# ==== PROCESS ====
run = st.button("🔍 Check Now")

if run:
    # Minimal validations (no extra BS)
    if not domain_text.strip():
        st.error("Domain content is empty. Paste or upload the domain file.")
    elif not target_line.strip():
        st.error("Search line is empty. Paste or upload the single line.")
    else:
        # Prepare domain lines and perform match
        domain_lines = get_lines_from_text(domain_text)
        is_match = check_match(domain_lines, target_line)

        # Build single-row, single-column matrix
        col_name = target_line.strip()
        df = pd.DataFrame({col_name: ["YES" if is_match else "NO"]}, index=[domain_page_name or "domain"])
        df.index.name = "Page"

        st.success("Done. Here’s your result matrix (one row × one column):")
        st.dataframe(df)

        # Download CSV
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        csv_bytes = df.to_csv().encode("utf-8")
        st.download_button(
            "⬇ Download CSV",
            csv_bytes,
            f"single_check_{now_str}.csv",
            "text/csv"
        )

        # Small sanity hints
        with st.expander("What was compared (for sanity)?"):
            p, _ = parse_three_fields(target_line)
            st.markdown(
                f"""
- **Target (3 fields):**  
  1. Exchange/Domain → `{p[0] or ''}` (ignoring spaces/commas, case-insensitive)  
  2. Seller ID → `{p[1] or ''}` (**case-sensitive exact**)  
  3. Relationship → `{p[2] or ''}` (ignoring spaces/commas, case-insensitive)
- **Domain lines scanned:** {len(domain_lines)}
"""
            )
