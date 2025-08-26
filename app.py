import streamlit as st
import pandas as pd
import requests
import random

# List of real User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
]

# Function to fetch ads.txt or app-ads.txt with random UA headers
def fetch_ads_txt(domain):
    urls_to_try = [f"https://{domain}/ads.txt", f"https://{domain}/app-ads.txt"]
    for url in urls_to_try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}  # rotate UA
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.text
        except Exception:
            continue
    return None

# Streamlit UI
st.title("Ads.txt / App-ads.txt Checker")

# Input box for domains
domain_input = st.text_area("Enter domains (one per line)")
domains = [d.strip() for d in domain_input.splitlines() if d.strip()]

# Input box for lines to check
lines_input = st.text_area("Enter lines to search (one per line, CSV format)")
lines = [l.strip() for l in lines_input.splitlines() if l.strip()]

# Lines management with element-wise case sensitivity
case_sensitives = {}
line_elements = {}
if lines:
    with st.expander("Lines Management", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            elements = [e.strip() for e in line.split(',') if e.strip()]
            # Only keep first two fields (domain + seller id), skip relation field
            line_elements[line] = elements[:2]
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

# Run button
if st.button("Check Now") and domains and lines:
    results = []
    for domain in domains:
        ads_content = fetch_ads_txt(domain)
        for line in lines:
            elements = line_elements[line]
            found = False
            if ads_content:
                for ads_line in ads_content.splitlines():
                    ads_parts = [e.strip() for e in ads_line.split(',') if e.strip()]
                    if len(ads_parts) >= 2:
                        match = True
                        for i, element in enumerate(elements):
                            if case_sensitives[line].get(element, False):
                                if ads_parts[i] != element:
                                    match = False
                                    break
                            else:
                                if ads_parts[i].lower() != element.lower():
                                    match = False
                                    break
                        if match:
                            found = True
                            break
            results.append({
                "Domain": domain,
                "Line": line,
                "Exists": "Yes" if found else "No"
            })
    df = pd.DataFrame(results)
    st.dataframe(df)
