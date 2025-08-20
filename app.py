import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime

st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === Inputs ===
st.subheader("Paste Domains (where ads.txt will be checked)")
domains_text = st.text_area("Enter domains (one per line)", height=150, placeholder="example.com\ndailymotion.com")

st.subheader("Paste Lines to Search (domain, id, relation optional)")
lines_text = st.text_area("Enter lines (one per line)", height=200,
                          placeholder="pubmatic.com, 166253, DIRECT\nvideo.unrulymedia.com, 906189653\nkrushmedia.com, AJxF6R667a9M6CaTvK")

# Search mode toggle
mode = st.radio("Search Mode", ["Flexible (Domain + ID only)", "Strict (Domain + ID + Relation)"])
ads_type = st.radio("Check in:", ["ads.txt", "app-ads.txt"])

# === Parse input lines into structured dataframe ===
def parse_lines(raw_text):
    rows = []
    for line in raw_text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 1:
            rows.append([parts[0], "", ""])
        elif len(parts) == 2:
            rows.append([parts[0], parts[1], ""])
        else:
            rows.append([parts[0], parts[1], parts[2]])
    return pd.DataFrame(rows, columns=["Line_Domain", "Pub_ID", "Relation"])

if lines_text.strip():
    st.subheader("🔎 Lines to Search (Editable)")
    lines_df = parse_lines(lines_text)
    edited_lines = st.data_editor(lines_df, num_rows="dynamic", use_container_width=True)
else:
    edited_lines = pd.DataFrame(columns=["Line_Domain", "Pub_ID", "Relation"])

# === Checker function ===
def fetch_ads(domain, ads_type):
    url = f"http://{domain}/{ads_type}"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            return resp.text.splitlines()
    except:
        return []
    return []

def check_lines(domain, ads_lines, search_lines, mode):
    results = []
    for _, row in search_lines.iterrows():
        line_domain, pub_id, relation = row["Line_Domain"], row["Pub_ID"], row["Relation"]

        found = False
        for adline in ads_lines:
            parts = [p.strip() for p in adline.split(",")]
            if len(parts) < 2:
                continue
            ad_domain, ad_id = parts[0], parts[1]
            ad_rel = parts[2] if len(parts) > 2 else ""

            if mode.startswith("Flexible"):
                if line_domain.lower() == ad_domain.lower() and pub_id == ad_id:
                    found = True
                    break
            else:  # Strict
                if (line_domain.lower() == ad_domain.lower() and
                        pub_id == ad_id and
                        relation.upper() == ad_rel.upper()):
                    found = True
                    break
        results.append("YES" if found else "NO")
    return results

# === Run Button ===
if st.button("🚀 Run Check"):
    domains = [d.strip() for d in domains_text.strip().splitlines() if d.strip()]
    output_rows = []

    for domain in domains:
        ads_lines = fetch_ads(domain, "app-ads.txt" if ads_type == "app-ads.txt" else "ads.txt")
        if not ads_lines:
            results = ["Not Found"] * len(edited_lines)
        else:
            results = check_lines(domain, ads_lines, edited_lines, mode)

        row = [domain] + results
        output_rows.append(row)

    # Prepare output dataframe
    header = ["Domain"] + [
        f"{r['Line_Domain']}, {r['Pub_ID']}" + (f", {r['Relation']}" if r['Relation'] else "")
        for _, r in edited_lines.iterrows()
    ]
    df_out = pd.DataFrame(output_rows, columns=header)

    # Show table
    st.subheader("✅ Results")
    st.dataframe(df_out, use_container_width=True)

    # CSV download
    filename = f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv = df_out.to_csv(index=False)
    st.download_button("⬇ Download CSV", csv, file_name=filename, mime="text/csv")
