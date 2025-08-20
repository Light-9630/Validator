import streamlit as st
import pandas as pd
import requests

# === SETTINGS ===
st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# Input: Domains where we search
domain_input = st.text_area("Paste domains where ads.txt/app-ads.txt will be checked (one per line)")
domains = [d.strip() for d in domain_input.splitlines() if d.strip()]

# Input: Lines user wants to validate
lines_input = st.text_area("Paste lines (supply chain) you want to validate")
lines = [l.strip() for l in lines_input.splitlines() if l.strip()]

# Search Mode
mode = st.radio("Search Mode", ["Strict (all parts must match)", "Flexible (only domain+id must match)"])
mode_strict = (mode == "Strict (all parts must match)")

# ads.txt or app-ads.txt toggle
ads_type = st.radio("Select type:", ["ads.txt", "app-ads.txt"])

# Parse lines into parts (domain, id, relation)
parsed_lines = []
for l in lines:
    parts = [p.strip() for p in l.split(",")]
    if len(parts) >= 2:
        domain = parts[0]
        pub_id = parts[1]
        relation = parts[2] if len(parts) >= 3 else None
        parsed_lines.append((domain, pub_id, relation))

if parsed_lines:
    st.write("🔎 Parsed Lines (editable if needed):")
    df_edit = pd.DataFrame(parsed_lines, columns=["Domain", "Pub ID", "Relation"])
    edited_lines = st.data_editor(df_edit, num_rows="dynamic")
else:
    edited_lines = []

# Function to fetch ads.txt
def fetch_ads(domain):
    url = f"https://{domain}/{ads_type}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return [line.strip() for line in resp.text.splitlines() if line.strip() and not line.startswith("#")]
        else:
            return None
    except:
        return None

# Run check
if st.button("Run Checker"):
    if not domains or not len(edited_lines):
        st.error("Please paste both domains and lines to check.")
    else:
        results = []
        for site in domains:
            ads_lines = fetch_ads(site)
            row = {"domain": site}
            if not ads_lines:
                # If file not found or error
                for _, line in edited_lines.iterrows():
                    row[f"{line['Domain']},{line['Pub ID']}"] = "NOT FOUND"
            else:
                for _, line in edited_lines.iterrows():
                    target_domain = str(line["Domain"]).strip().lower()
                    target_id = str(line["Pub ID"]).strip()
                    target_rel = str(line["Relation"]).strip() if pd.notna(line["Relation"]) else None

                    found = False
                    for adl in ads_lines:
                        parts = [p.strip().lower() for p in adl.split(",")]
                        if len(parts) >= 2:
                            d, pid = parts[0], parts[1]
                            rel = parts[2] if len(parts) >= 3 else None

                            if mode_strict:
                                if d == target_domain and pid == target_id and rel == (target_rel or rel):
                                    found = True
                                    break
                            else:  # Flexible: only domain+id
                                if d == target_domain and pid == target_id:
                                    found = True
                                    break

                    row[f"{line['Domain']},{line['Pub ID']}"] = "YES" if found else "NO"

            results.append(row)

        df_out = pd.DataFrame(results)
        st.dataframe(df_out)

        # Export CSV
        csv = df_out.to_csv(index=False)
        st.download_button("💾 Download CSV", csv, "results.csv", "text/csv")
