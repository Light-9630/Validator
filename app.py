import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import io, time
from requests.adapters import HTTPAdapter, Retry

# === PAGE CONFIG ===
st.set_page_config(page_title="Ads.txt / App-Ads.txt Triplet Checker", layout="wide")
st.title("📄 Ads.txt / App-Ads.txt Triplet Checker")

# === SETTINGS ===
threads = st.number_input("⚙ Number of threads", min_value=1, max_value=30, value=10)

# === USER INPUT ===
domains_text = st.text_area("🌍 Enter domains (one per line)", height=150, placeholder="example.com\ndailymotion.com\n...")
lines_text = st.text_area("🔍 Enter triplets (domain, id, relation) one per line", height=150,
                          placeholder="google.com, pub-1234567890, DIRECT\nopenx.com, 98765, RESELLER\n...")

if st.button("Run Check ✅"):
    start_time = time.time()

    # Prepare domain list
    domains = [d.strip() for d in domains_text.splitlines() if d.strip()]
    if not domains:
        st.error("❌ Please enter at least one domain.")
        st.stop()

    # Prepare triplets list
    triplets = []
    for line in lines_text.splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) >= 3:  # take only first 3
            triplets.append((parts[0], parts[1], parts[2]))

    if not triplets:
        st.error("❌ Please enter at least one valid triplet (domain, id, relation).")
        st.stop()

    # === HTTP Session with Retry ===
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    def fetch_ads(domain):
        urls = [f"https://{domain}/ads.txt", f"http://{domain}/ads.txt",
                f"https://{domain}/app-ads.txt", f"http://{domain}/app-ads.txt"]
        for url in urls:
            try:
                r = session.get(url, timeout=8)
                if r.status_code == 200 and "DIRECT" in r.text.upper():  # quick filter
                    return domain, r.text.splitlines()
            except:
                continue
        return domain, []

    results = {}
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(fetch_ads, d): d for d in domains}
        for f in as_completed(futures):
            domain, lines = f.result()
            results[domain] = lines

    # === PROCESSING ===
    data = []
    for domain, ads_lines in results.items():
        row = {"domain": domain}
        ads_lines_clean = [line.strip().lower() for line in ads_lines if line.strip() and not line.startswith("#")]

        for triplet in triplets:
            d, i, r = [x.lower() for x in triplet]
            found = any(
                (d in line and i in line and r in line)
                for line in ads_lines_clean
            )
            key = f"{triplet[0]}, {triplet[1]}, {triplet[2]}"
            row[key] = "✅ YES" if found else "❌ NO"
        data.append(row)

    df = pd.DataFrame(data)

    # === SHOW RESULTS ===
    st.subheader("📊 Results")
    st.dataframe(df, use_container_width=True)

    # Export
    filename = f"ads_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button("📥 Download CSV", data=csv_buf.getvalue(), file_name=filename, mime="text/csv")

    st.success(f"✅ Completed in {time.time() - start_time:.2f} seconds")
