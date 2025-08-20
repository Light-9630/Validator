import streamlit as st
import pandas as pd
import requests
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Ads.txt / App-Ads.txt Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Bulk Checker")

# === INPUT TEXT AREA ===
st.write("Paste your lines below (format: `domain, id, relation(optional)`)")

user_input = st.text_area("Input Lines", height=200, placeholder="pubmatic.com, 166253, DIRECT\nkrushmedia.com, AJxF6R667a9M6CaTvK")

if user_input.strip():
    # Split into rows and columns
    data = []
    for line in user_input.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        # Ensure 3 columns
        while len(parts) < 3:
            parts.append("")
        data.append(parts[:3])

    df = pd.DataFrame(data, columns=["Domain", "Publisher ID", "Relation"])
    st.write("### ✍️ Editable Input Table")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    # === OPTIONS ===
    col1, col2 = st.columns(2)
    with col1:
        file_type = st.radio("File to check", ["ads.txt", "app-ads.txt"], horizontal=True)
    with col2:
        match_mode = st.radio("Match Mode", ["Strict (3 parts)", "Flexible (Domain + ID only)"], horizontal=True)

    threads = st.slider("⚙️ Number of threads", 1, 20, 5)

    if st.button("🚀 Run Checker"):
        results = []

        def check_line(row):
            domain, pub_id, relation = row["Domain"], row["Publisher ID"], row["Relation"]
            url = f"http://{domain}/{file_type}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    return [domain, pub_id, relation, "❌ No file"]

                found = False
                for line in resp.text.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        if match_mode.startswith("Strict"):
                            if len(parts) >= 3 and parts[0] == domain and parts[1] == pub_id and parts[2].upper() == relation.upper():
                                found = True
                                break
                        else:  # Flexible
                            if parts[0] == domain and parts[1] == pub_id:
                                found = True
                                break

                return [domain, pub_id, relation, "✅ Yes" if found else "❌ No"]

            except Exception as e:
                return [domain, pub_id, relation, f"⚠️ Error: {str(e)}"]

        # Run in parallel
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(check_line, row) for _, row in edited_df.iterrows()]
            for f in as_completed(futures):
                results.append(f.result())

        result_df = pd.DataFrame(results, columns=["Domain", "Publisher ID", "Relation", "Result"])
        st.write("### ✅ Results")
        st.dataframe(result_df, use_container_width=True)

        # Download CSV
        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Results CSV", csv, "results.csv", "text/csv")
