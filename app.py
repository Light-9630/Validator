import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter, Retry

st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === SETTINGS ===
search_mode = st.radio("Search Mode", ["Strict (all parts must match)", "Flexible (match first 2 parts only)"])
case_toggle = st.checkbox("Default: Case Sensitive?", value=True)
ads_type = st.radio("Select Type", ["ads.txt", "app-ads.txt"])

# === INPUTS ===
st.subheader("Step 1: Paste Target Domains (where search will happen)")
domains_input = st.text_area("One domain per line (e.g. dailymotion.com, youtube.com)", height=150)

st.subheader("Step 2: Paste Lines to Search (domain, id, relation etc.)")
lines_input = st.text_area("Paste lines here (comma-separated values)", height=200)

# Parse domains
domains = [d.strip() for d in domains_input.splitlines() if d.strip()]

# Parse lines into structured parts
search_lines = []
if lines_input:
    for line in lines_input.splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if parts:
            search_lines.append(parts)

# Convert to preview DataFrame with dynamic columns
if search_lines:
    max_cols = max(len(line) for line in search_lines)
    col_names = [f"Part {i+1}" for i in range(max_cols)]
    padded_lines = [line + [""] * (max_cols - len(line)) for line in search_lines]
    df_preview = pd.DataFrame(padded_lines, columns=col_names)

    st.subheader("Preview & Column Settings")
    st.dataframe(df_preview)

    # Per-column case toggle
    case_settings = {}
    for col in df_preview.columns:
        case_settings[col] = st.checkbox(f"Case Sensitive for {col}", value=case_toggle)

else:
    df_preview = pd.DataFrame()

# === Function to fetch ads.txt ===
def fetch_ads(domain):
    url = f"http://{domain}/{ads_type}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AdsChecker/1.0)"}
    try:
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))
        r = session.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.text.splitlines()
    except:
        return []
    return []

# === RUN CHECK ===
if st.button("Run Checker"):
    if not domains or df_preview.empty:
        st.error("Please paste domains and search lines first.")
    else:
        results = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            ads_data = list(executor.map(fetch_ads, domains))

        for dom, ads_lines in zip(domains, ads_data):
            row_result = []
            for _, parts in df_preview.iterrows():
                search_parts = []
                for idx, val in enumerate(parts):
                    val = str(val).strip()
                    if not case_settings[f"Part {idx+1}"]:
                        val = val.lower()
                    search_parts.append(val)

                found = False
                for ads_line in ads_lines:
                    ads_split = [p.strip() for p in ads_line.split(",")]
                    if not case_toggle:
                        ads_split = [p.lower() for p in ads_split]

                    if search_mode.startswith("Strict"):
                        if len(search_parts) <= len(ads_split) and all(
                            search_parts[i] == (ads_split[i] if case_settings[f"Part {i+1}"] else ads_split[i].lower())
                            for i in range(len(search_parts))
                        ):
                            found = True
                            break
                    else:  # Flexible mode
                        if len(search_parts) >= 2 and len(ads_split) >= 2:
                            if search_parts[0] == (ads_split[0] if case_settings["Part 1"] else ads_split[0].lower()) and \
                               search_parts[1] == (ads_split[1] if case_settings["Part 2"] else ads_split[1].lower()):
                                found = True
                                break

                row_result.append("YES" if found else "NO")
            results[dom] = row_result

        output_df = pd.DataFrame(results, index=[", ".join(line) for line in search_lines]).T
        st.subheader("Results")
        st.dataframe(output_df)
