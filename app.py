# final_streamlit_ads_checker_with_filetype.py
import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re
import os
import json
import datetime
import base64

# ---------------- Page Setup ----------------
st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("🔎 Ads.txt / App-ads.txt Bulk Checker")

DATA_FILE = "data.json"
DEFAULT_BRANCH = "main"

# ---------------- Helpers ----------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"domains": {}, "snapshots": {}}
    return {"domains": {}, "snapshots": {}}

def save_local_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def github_commit_datafile(data, commit_message="Update data.json"):
    token = st.secrets.get("GITHUB_TOKEN") if st.secrets else None
    repo = st.secrets.get("GITHUB_REPO") if st.secrets else None
    branch = st.secrets.get("GITHUB_BRANCH", DEFAULT_BRANCH)
    if not token or not repo:
        return False, "GitHub not configured"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}/contents/{DATA_FILE}"
    r = requests.get(f"{api}?ref={branch}", headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    b64 = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    payload = {"message": commit_message, "content": b64, "branch": branch}
    if sha:
        payload["sha"] = sha
    resp = requests.put(api, headers=headers, json=payload)
    return (resp.status_code in (200, 201)), resp.text

# ---------------- Load Data ----------------
data = load_data()
data.setdefault("domains", {})
data.setdefault("snapshots", {})

# ---------------- Input Tabs ----------------
tab1, tab2 = st.tabs(["📋 Paste Domains", "📂 Upload Domains File"])
domains_input_from_ui = []

with tab1:
    st.header("Input Domains (one per line)")
    domain_input = st.text_area("Paste domains", height=200, placeholder="hola.com\nexample.com")
    if domain_input:
        domains_input_from_ui = [d.strip() for d in domain_input.splitlines() if d.strip()]

with tab2:
    st.header("Upload File")
    uploaded_file = st.file_uploader("Upload CSV/TXT file", type=["csv", "txt"])
    if uploaded_file:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
        domains_input_from_ui.extend(uploaded_domains)

domains_input_from_ui = list(dict.fromkeys(domains_input_from_ui))
if domains_input_from_ui:
    st.info(f"✅ {len(domains_input_from_ui)} unique domains loaded.")

# ---------------- Search Lines ----------------
st.header("🔍 Search Lines")
line_input = st.text_area("Paste search lines", height=200)
file_type = st.selectbox("Select file type", ["ads.txt", "app-ads.txt"])

lines = [l.strip() for l in line_input.splitlines() if l.strip()]
line_elements = {line: [line] for line in lines}

# ---------------- Sidebar ----------------
st.sidebar.header("⚡ Settings")
proxy_input = st.sidebar.text_input("Proxy (optional)", placeholder="http://host:port")
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None
ua_choice = st.sidebar.radio("User-Agent Mode", ["Live Browser UA", "AdsBot-Google UA"], index=0)

LIVE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Safari/537.36"
    if ua_choice == "Live Browser UA"
    else "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"
)
st.sidebar.write(f"🟢 UA: {LIVE_UA}")

session = requests.Session()
session.headers.update({"user-agent": LIVE_UA})
if proxies:
    session.proxies.update(proxies)

# ---------------- Fetch ----------------
def fetch_with_retry(domain, ftype, session_local=session, retries=2, timeout=8):
    urls = [f"https://{domain}/{ftype}", f"http://{domain}/{ftype}"]
    for url in urls:
        for _ in range(retries):
            try:
                r = session_local.get(url, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    return r.text, None
            except Exception as e:
                last_error = str(e)
    return None, last_error

# ---------------- Check Line ----------------
def check_line_in_content(content, elements):
    if not content:
        return False
    for c_line in content.splitlines():
        if any(e.lower() in c_line.lower() for e in elements):
            return True
    return False

# ---------------- Data Manager ----------------
st.sidebar.markdown("---")
st.sidebar.header("🔧 Data Manager")

with st.sidebar.form("domain_form", clear_on_submit=False):
    dm_domains = st.text_area("Domains to track", height=120, placeholder="hola.com\nsharechat.com")
    dm_type = st.selectbox("File type", ["ads.txt", "app-ads.txt"])
    dm_lines = st.text_area("Lines to monitor", height=120, placeholder="pubmatic.com\ngoogle.com")
    submitted = st.form_submit_button("Add / Update Domains")
    delete_domain = st.form_submit_button("Delete Domains")

if submitted and dm_domains:
    domain_list = [d.strip() for d in dm_domains.splitlines() if d.strip()]
    lines_list = [l.strip() for l in dm_lines.splitlines() if l.strip()]
    for d in domain_list:
        data["domains"][d] = {"type": dm_type, "lines": lines_list}
    save_local_data(data)
    st.sidebar.success(f"Added/Updated {len(domain_list)} domains.")

if delete_domain and dm_domains:
    domain_list = [d.strip() for d in dm_domains.splitlines() if d.strip()]
    removed = 0
    for d in domain_list:
        if d in data["domains"]:
            data["domains"].pop(d)
            removed += 1
    save_local_data(data)
    st.sidebar.success(f"Deleted {removed} domains." if removed else "No domains found.")

# ---------------- Daily Report ----------------
st.header("📅 Daily Report (Tracked Domains)")
if st.button("🗓️ Generate Today's Report"):
    if not data["domains"]:
        st.warning("No domains tracked.")
    else:
        today = datetime.date.today().isoformat()
        domains = list(data["domains"].items())
        report = {"Page": [d for d, _ in domains], "File Type": [info["type"] for _, info in domains]}
        all_lines = sorted({l for info in data["domains"].values() for l in info["lines"]})
        for l in all_lines:
            report[l] = [""] * len(domains)

        errors = {}
        progress = st.progress(0)

        with ThreadPoolExecutor(max_workers=20) as exe:
            futures = {exe.submit(fetch_with_retry, d, info["type"]): (idx, d, info)
                       for idx, (d, info) in enumerate(domains)}
            for processed, fut in enumerate(as_completed(futures), 1):
                idx, d, info = futures[fut]
                content, err = fut.result()
                if err:
                    errors[d] = err
                    for l in all_lines:
                        report[l][idx] = "Error"
                else:
                    for l in all_lines:
                        elements = [e.strip() for e in l.split(",")] if "," in l else [l]
                        found = check_line_in_content(content, elements)
                        report[l][idx] = "Yes" if found else "No"
                progress.progress(processed / len(domains))

        df = pd.DataFrame(report)
        st.success("✅ Daily report generated.")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode()
        st.download_button("💾 Download Report", data=csv, file_name=f"daily_report_{today}.csv", mime="text/csv")

# ---------------- Manual Ad-hoc Check ----------------
st.markdown("---")
st.header("🚀 Ad-hoc Checking")
if st.button("Start Checking", disabled=not (domains_input_from_ui and lines)):
    start = time.time()
    results = {"Page": domains_input_from_ui}
    for l in lines:
        results[l] = [""] * len(domains_input_from_ui)
    errors = {}
    progress = st.progress(0)
    with ThreadPoolExecutor(max_workers=30) as exe:
        futs = {exe.submit(fetch_with_retry, d, file_type): i for i, d in enumerate(domains_input_from_ui)}
        for processed, fut in enumerate(as_completed(futs), 1):
            idx = futs[fut]
            d = domains_input_from_ui[idx]
            try:
                content, err = fut.result()
            except Exception as e:
                content, err = None, str(e)
            if err:
                errors[d] = err
                for l in lines:
                    results[l][idx] = "Error"
            else:
                for l in lines:
                    found = check_line_in_content(content, [l])
                    results[l][idx] = "Yes" if found else "No"
            progress.progress(processed / len(domains_input_from_ui))

    df = pd.DataFrame(results)
    st.success(f"Done in {time.time()-start:.2f}s")
    st.dataframe(df)
    csv = df.to_csv(index=False).encode()
    st.download_button("💾 Download CSV", data=csv, file_name="ads_txt_results.csv", mime="text/csv")

with st.expander("🗄️ View raw data.json"):
    st.json(data)
