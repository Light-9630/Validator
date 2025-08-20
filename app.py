import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
import io
from datetime import datetime

st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === SETTINGS ===
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=50, value=10)
mode = st.radio("🔎 Search Mode", ["Flexible (ignore extra parts)", "Strict (all parts must match)"])
ads_type = st.radio("📂 Check file type", ["ads.txt", "app-ads.txt"])

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
]

# === INPUT LINES ===
st.subheader("Paste lines to check")
pasted_lines = st.text_area("Enter domains, IDs, relation (one per line)", height=200)

def parse_lines(lines):
    data = []
    for line in lines:
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if parts:
            data.append(parts)
    return data

lines_data = parse_lines(pasted_lines.splitlines()) if pasted_lines else []

if lines_data:
    # Convert to DataFrame (variable cols possible)
    max_len = max(len(row) for row in lines_data)
    for row in lines_data:
        while len(row) < max_len:
            row.append("")
    columns = [f"Part{i+1}" for i in range(max_len)]
    df = pd.DataFrame(lines_data, columns=columns)

    st.subheader("🔍 Preview & Edit Lines")
    st.markdown("You can edit values below before running check. Also set case sensitivity per column.")

    # Case sensitivity selection
    case_settings = {}
    cols = st.columns(len(columns))
    for i, col in enumerate(columns):
        with cols[i]:
            case_settings[col] = st.checkbox(f"Case-sensitive {col}", value=False)

    # Editable DataFrame
    df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    # === CHECK BUTTON ===
    if st.button("🚀 Run Checker"):
        results = []

        def fetch_ads(domain):
            url = f"http://{domain}/{ads_type}"
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
            session.mount("http://", HTTPAdapter(max_retries=retries))
            session.mount("https://", HTTPAdapter(max_retries=retries))

            for ua in user_agents:
                try:
                    headers = {"User-Agent": ua}
                    r = session.get(url, timeout=8, headers=headers)
                    if r.status_code == 200:
                        return r.text
                except:
                    continue
            return ""

        def check_domain(domain, ads_text, targets):
            lines = ads_text.splitlines()
            output = []
            for target in targets:
                found = False
                for line in lines:
                    parts = [p.strip() for p in line.split(",")]
                    if mode.startswith("Flexible"):
                        match = True
                        for i in range(len(target)):
                            left, right = target[i], parts[i] if i < len(parts) else ""
                            if not case_settings[f"Part{i+1}"]:
                                left, right = left.lower(), right.lower()
                            if left and left != right:
                                match = False
                                break
                        if match:
                            found = True
                            break
                    else:  # Strict
                        if len(parts) < len(target):
                            continue
                        match = True
                        for i in range(len(target)):
                            left, right = target[i], parts[i]
                            if not case_settings[f"Part{i+1}"]:
                                left, right = left.lower(), right.lower()
                            if left and left != right:
                                match = False
                                break
                        if match:
                            found = True
                            break
                output.append("YES" if found else "NO")
            return output

        # Group by domain
        grouped = {}
        for row in df.values.tolist():
            domain = row[0]
            grouped.setdefault(domain, []).append(row)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_domain = {executor.submit(fetch_ads, d): d for d in grouped}
            for future in as_completed(future_to_domain):
                domain = future_to_domain[future]
                ads_text = future.result()
                checks = check_domain(domain, ads_text, grouped[domain]) if ads_text else ["ERROR"] * len(grouped[domain])
                results.append([domain] + checks)

        # Output DataFrame
        max_len = max(len(r) for r in results)
        for r in results:
            while len(r) < max_len:
                r.append("")
        output_cols = ["Domain"] + [", ".join(map(str, row)) for row in df.values.tolist()]
        out_df = pd.DataFrame(results, columns=output_cols)

        st.subheader("✅ Results")
        st.dataframe(out_df, use_container_width=True)

        # Save to CSV
        buf = io.StringIO()
        out_df.to_csv(buf, index=False)
        st.download_button("📥 Download CSV", buf.getvalue(), file_name=f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")

