# final_ads_checker_with_manual_and_real_wipe.py
import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time, json, os, re, datetime, base64
from io import StringIO

st.set_page_config(page_title="Ads.txt / App-Ads.txt Bulk Checker", layout="wide")
st.title("🔎 Ads.txt / App-Ads.txt Bulk Checker")

DATA_FILE = "data.json"
DEFAULT_BRANCH = "main"

# ---------------- Helpers ----------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
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
if "data" not in st.session_state:
    st.session_state.data = load_data()
data = st.session_state.data
data.setdefault("domains", {})
data.setdefault("snapshots", {})

# ---------------- Sidebar Settings ----------------
st.sidebar.header("⚙️ Settings")
proxy_input = st.sidebar.text_input("Proxy (optional)", placeholder="http://host:port")
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None
ua_choice = st.sidebar.radio("User-Agent", ["Live Browser UA", "AdsBot-Google UA"], index=0)
LIVE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Safari/537.36"
    if ua_choice == "Live Browser UA"
    else "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"
)
st.sidebar.caption(f"🟢 UA: {LIVE_UA}")

session = requests.Session()
session.headers.update({"user-agent": LIVE_UA})
if proxies:
    session.proxies.update(proxies)

# ---------------- Fetch Helpers ----------------
def fetch_with_retry(domain, ftype, retries=2, timeout=8):
    urls = [f"https://{domain}/{ftype}", f"http://{domain}/{ftype}"]
    for url in urls:
        for _ in range(retries):
            try:
                r = session.get(url, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    return r.text, None
            except Exception as e:
                err = str(e)
    return None, err

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
    st.sidebar.success(f"✅ Added/Updated {len(domain_list)} domain(s).")

if delete_domain and dm_domains:
    domain_list = [d.strip() for d in dm_domains.splitlines() if d.strip()]
    removed = 0
    for d in domain_list:
        if d in data["domains"]:
            del data["domains"][d]
            removed += 1
    save_local_data(data)
    st.sidebar.success(f"✅ Deleted {removed} domain(s)." if removed else "No matching domains found.")

# ---------------- Wipe Data Button ----------------
st.sidebar.markdown("---")
st.sidebar.header("🧨 Danger Zone")

if st.sidebar.button("⚠️ Wipe All Data (Full Reset)"):
    confirm = st.sidebar.checkbox("☑️ Confirm wipe before proceeding")
    if confirm:
        try:
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.session_state.data = {"domains": {}, "snapshots": {}}
            save_local_data(st.session_state.data)
            if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
                github_commit_datafile(st.session_state.data, commit_message="Manual wipe of data.json")
            st.success("✅ data.json wiped successfully. App will reload.")
            st.balloons()
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Failed to wipe data: {e}")
    else:
        st.warning("Please check confirm box before wiping.")

# ---------------- Tabs: Manual Checker + Daily Report ----------------
tab_manual, tab_report = st.tabs(["🧠 Manual Checker", "📅 Daily Report"])

# ----- Manual Checker -----
with tab_manual:
    st.header("🚀 Manual Check")
    tab1, tab2 = st.tabs(["📋 Paste Domains", "📂 Upload Domains File"])
    domains_input_from_ui = []
    with tab1:
        st.subheader("Input Domains")
        domain_input = st.text_area("Domains (one per line)", height=200, placeholder="hola.com\nexample.com")
        if domain_input:
            domains_input_from_ui = [d.strip() for d in domain_input.splitlines() if d.strip()]
    with tab2:
        st.subheader("Upload Domains File")
        uploaded_file = st.file_uploader("Upload CSV/TXT", type=["csv", "txt"])
        if uploaded_file:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
            domains_input_from_ui.extend(uploaded_domains)
    domains_input_from_ui = list(dict.fromkeys(domains_input_from_ui))

    st.subheader("Search Lines")
    line_input = st.text_area("Lines to search for", height=200, placeholder="pubmatic.com\ngoogle.com")
    lines = [l.strip() for l in line_input.splitlines() if l.strip()]
    file_type = st.selectbox("Select file type", ["ads.txt", "app-ads.txt"])

    if st.button("Start Manual Check", disabled=not (domains_input_from_ui and lines)):
        st.info(f"Checking {len(domains_input_from_ui)} domains...")
        start = time.time()
        results = {"Page": domains_input_from_ui}
        for l in lines:
            results[l] = [""] * len(domains_input_from_ui)
        progress = st.progress(0)
        with ThreadPoolExecutor(max_workers=30) as exe:
            futs = {exe.submit(fetch_with_retry, d, file_type): i for i, d in enumerate(domains_input_from_ui)}
            for processed, fut in enumerate(as_completed(futs), 1):
                idx = futs[fut]
                d = domains_input_from_ui[idx]
                content, err = fut.result()
                if err:
                    for l in lines:
                        results[l][idx] = "Error"
                else:
                    for l in lines:
                        found = check_line_in_content(content, [l])
                        results[l][idx] = "Yes" if found else "No"
                progress.progress(processed / len(domains_input_from_ui))
        df = pd.DataFrame(results)
        st.success(f"✅ Done in {time.time()-start:.2f}s")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode()
        st.download_button("💾 Download Results", data=csv, file_name="manual_ads_check.csv", mime="text/csv")

# ----- Daily Report -----
with tab_report:
    st.header("📅 Daily Report (Tracked Domains)")
    if st.button("Generate Daily Report"):
        if not data["domains"]:
            st.warning("No domains tracked.")
        else:
            today = datetime.date.today().isoformat()
            domains = list(data["domains"].items())
            report = {"Page": [d for d, _ in domains], "File Type": [info["type"] for _, info in domains]}
            all_lines = sorted({l for info in data["domains"].values() for l in info["lines"]})
            for l in all_lines:
                report[l] = [""] * len(domains)
            progress = st.progress(0)
            with ThreadPoolExecutor(max_workers=20) as exe:
                futures = {exe.submit(fetch_with_retry, d, info["type"]): (idx, d, info)
                           for idx, (d, info) in enumerate(domains)}
                for processed, fut in enumerate(as_completed(futures), 1):
                    idx, d, info = futures[fut]
                    content, err = fut.result()
                    if err:
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

# ---------------- Raw JSON ----------------
with st.expander("🗄️ View raw data.json"):
    st.json(data)
