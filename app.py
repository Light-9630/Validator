# full_streamlit_ads_checker_fixed.py
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

# ---------------- Constants / Files ----------------
DATA_FILE = "data.json"
DEFAULT_BRANCH = "main"

# ---------------- Helpers: Data persistence ----------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"domains": {}, "snapshots": {}}
    else:
        return {"domains": {}, "snapshots": {}}

def save_local_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def github_commit_datafile(data, commit_message="Update data.json from Streamlit app"):
    token = st.secrets.get("GITHUB_TOKEN") if st.secrets else None
    repo = st.secrets.get("GITHUB_REPO") if st.secrets else None
    branch = st.secrets.get("GITHUB_BRANCH") if st.secrets and "GITHUB_BRANCH" in st.secrets else DEFAULT_BRANCH

    if not token or not repo:
        return False, "GitHub token or repo not configured in Streamlit secrets."

    owner_repo = repo.strip()
    path = DATA_FILE

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    api_base = "https://api.github.com"

    get_url = f"{api_base}/repos/{owner_repo}/contents/{path}?ref={branch}"
    r = requests.get(get_url, headers=headers)
    file_sha = None
    if r.status_code == 200:
        file_sha = r.json().get("sha")

    content_bytes = json.dumps(data, indent=2).encode("utf-8")
    content_b64 = base64.b64encode(content_bytes).decode("utf-8")

    put_url = f"{api_base}/repos/{owner_repo}/contents/{path}"
    payload = {"message": commit_message, "content": content_b64, "branch": branch}
    if file_sha:
        payload["sha"] = file_sha

    put = requests.put(put_url, headers=headers, json=payload)
    if put.status_code in (200, 201):
        return True, "Committed to GitHub."
    else:
        return False, f"GitHub API error {put.status_code}: {put.text}"

# ---------------- Load stored data ----------------
data = load_data()
data.setdefault("domains", {})
data.setdefault("snapshots", {})

# ---------------- Input Tabs (paste/upload domains) ----------------
tab1, tab2 = st.tabs(["📋 Paste Domains", "📂 Upload Domains File"])

domains_input_from_ui = []
with tab1:
    st.header("Input Domains (one per line)")
    domain_input = st.text_area("Paste domains (one per line)", height=200, placeholder="hola.com\nexample.com")
    if domain_input:
        domains_input_from_ui = [d.strip() for d in domain_input.splitlines() if d.strip()]

with tab2:
    st.header("Upload File")
    uploaded_file = st.file_uploader("Upload CSV/TXT file with domains", type=["csv", "txt"])
    if uploaded_file:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
        domains_input_from_ui.extend(uploaded_domains)

domains_input_from_ui = list(dict.fromkeys(domains_input_from_ui))
if domains_input_from_ui:
    st.info(f"✅ {len(domains_input_from_ui)} unique domains loaded into ad-hoc check queue.")

# ---------------- Search Lines (ad-hoc checking) ----------------
st.header("🔍 Ad-hoc Search Lines (for Start Checking)")
line_input = st.text_area(
    "Paste search lines (CSV format or single word/number, one per line).",
    height=200
)

file_type = st.selectbox("Select file type for ad-hoc check", ["ads.txt", "app-ads.txt"])

field_limit = st.selectbox(
    "Select number of fields to check",
    [1, 2, 3, 4],
    index=1
)

lines = [l.strip() for l in line_input.splitlines() if l.strip()]
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("⚙ Ad-hoc Line Settings (case sensitivity)", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive", value=False)
        for line in lines:
            if "," in line:
                elements = [e.strip() for e in line.split(",") if e.strip()]
            else:
                elements = [line]
            line_elements[line] = elements[:field_limit]
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

# ---------------- Sidebar: Proxy + UA Mode ----------------
st.sidebar.header("⚡ Settings")

proxy_input = st.sidebar.text_input("Proxy (optional)", placeholder="http://host:port")
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None

ua_choice = st.sidebar.radio("User-Agent Mode", ["Live Browser UA", "AdsBot-Google UA"], index=0)

LIVE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    if ua_choice == "Live Browser UA"
    else "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"
)

st.sidebar.write(f"🟢 Using User-Agent: {LIVE_UA}")

session = requests.Session()
session.headers.update({"user-agent": LIVE_UA})
if proxies:
    session.proxies.update(proxies)

# ---------------- Fetch with retry ----------------
def fetch_with_retry(domain, file_type_local, session_local=session, max_retries=2, timeout=8):
    urls = [f"https://{domain}/{file_type_local}", f"http://{domain}/{file_type_local}"]
    for url in urls:
        for attempt in range(max_retries):
            try:
                r = session_local.get(url, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    return r.text, None
            except Exception as e:
                last_error = str(e)
    return None, last_error

# ---------------- Check line content ----------------
def check_line_in_content(content, line_elements_local, case_sensitives_line):
    if not content:
        return False
    content_lines = content.splitlines()
    cleaned_lines = [
        re.split(r"\s*#", l.strip())[0].strip()
        for l in content_lines
        if l.strip() and not l.strip().startswith("#")
    ]
    for c_line in cleaned_lines:
        parts = [e.strip() for e in c_line.split(",")]
        all_match = True
        for i, el in enumerate(line_elements_local):
            if i >= len(parts):
                all_match = False
                break
            if case_sensitives_line.get(el, False):
                if el != parts[i]:
                    all_match = False
                    break
            else:
                if el.lower() != parts[i].lower():
                    all_match = False
                    break
        if all_match:
            return True
    return False

# ---------------- Data Manager (Add/Edit/Delete multiple domains) ----------------
st.sidebar.markdown("---")
st.sidebar.header("🔧 Data Manager (Persistent Tracker)")

with st.sidebar.form("domain_form", clear_on_submit=False):
    dm_domains = st.text_area(
        "Domains to track (one per line)",
        height=120,
        placeholder="hola.com\nsharechat.com\nm.dailyhunt.in"
    )
    dm_type = st.selectbox("File type", ["ads.txt", "app-ads.txt"])
    dm_lines = st.text_area(
        "Lines to monitor (one per line)",
        height=120,
        placeholder="pubmatic.com\ngoogle.com"
    )
    submitted = st.form_submit_button("Add / Update Domain(s)")
    delete_domain = st.form_submit_button("Delete Domain(s)")

if submitted and dm_domains:
    domain_list = [d.strip() for d in dm_domains.splitlines() if d.strip()]
    lines_list = [l.strip() for l in dm_lines.splitlines() if l.strip()]
    for domain in domain_list:
        data["domains"][domain] = {"type": dm_type, "lines": lines_list}
    save_local_data(data)
    if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
        ok, msg = github_commit_datafile(data, commit_message=f"Streamlit: add/update {len(domain_list)} domain(s)")
        st.sidebar.success(f"Added/Updated {len(domain_list)} domain(s). {msg}")
    else:
        st.sidebar.success(f"Added/Updated {len(domain_list)} domain(s) locally.")

if delete_domain and dm_domains:
    domain_list = [d.strip() for d in dm_domains.splitlines() if d.strip()]
    removed = 0
    for domain in domain_list:
        if domain in data["domains"]:
            data["domains"].pop(domain)
            removed += 1
    save_local_data(data)
    if removed > 0:
        if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
            ok, msg = github_commit_datafile(data, commit_message=f"Streamlit: deleted {removed} domain(s)")
            st.sidebar.success(f"Deleted {removed} domain(s). {msg}")
        else:
            st.sidebar.success(f"Deleted {removed} domain(s) locally.")
    else:
        st.sidebar.warning("No matching domains found to delete.")

st.sidebar.markdown("**Tracked domains:**")
if data["domains"]:
    for d, info in data["domains"].items():
        st.sidebar.markdown(f"- `{d}` ({info.get('type')}) — {len(info.get('lines', []))} line(s)")
else:
    st.sidebar.info("No domains tracked yet.")

# ---------------- Generate Daily Report ----------------
st.header("📅 Daily Report (Tracked Domains)")
if st.button("🗓️ Generate Today's Report"):
    if not data["domains"]:
        st.warning("No domains tracked yet.")
    else:
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        snapshots = {}
        report_rows = []
        progress_bar = st.progress(0)
        dom_items = list(data["domains"].items())
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(fetch_with_retry, d, info["type"]): (d, info) for d, info in dom_items}
            for idx, future in enumerate(as_completed(futures), 1):
                domain, info = futures[future]
                try:
                    content, err = future.result()
                except Exception as e:
                    content, err = None, str(e)
                tracked_lines = info["lines"]
                found_lines = []
                if not err:
                    for line in tracked_lines:
                        elements = [e.strip() for e in line.split(",")] if "," in line else [line]
                        found = check_line_in_content(content, elements, {line: False})
                        if found:
                            found_lines.append(line)
                snapshots[domain] = found_lines
                old = set(data["snapshots"].get(yesterday, {}).get(domain, []))
                new = set(found_lines)
                added = new - old
                removed = old - new
                unchanged = new & old
                report_rows.append({
                    "Domain": domain,
                    "Added": ", ".join(added) if added else "-",
                    "Removed": ", ".join(removed) if removed else "-",
                    "Unchanged": ", ".join(unchanged) if unchanged else "-",
                    "Error": err or "-"
                })
                progress_bar.progress(idx / len(dom_items))

        data["snapshots"][today] = snapshots
        save_local_data(data)
        if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
            github_commit_datafile(data, commit_message=f"Daily snapshot {today}")
        df = pd.DataFrame(report_rows).set_index("Domain")
        st.dataframe(df, use_container_width=True)
        csv_data = df.reset_index().to_csv(index=False).encode("utf-8")
        st.download_button("💾 Download Daily Report", data=csv_data, file_name=f"daily_report_{today}.csv", mime="text/csv")

# ---------------- Ad-hoc Check ----------------
st.markdown("---")
st.header("🚀 Ad-hoc Checking")
if st.button("Start Checking", disabled=not (domains_input_from_ui and lines)):
    domains = domains_input_from_ui
    start_time = time.time()
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    errors = {}
    progress_bar = st.progress(0)
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_index = {executor.submit(fetch_with_retry, d, file_type): i for i, d in enumerate(domains)}
        for processed, future in enumerate(as_completed(future_to_index), 1):
            idx = future_to_index[future]
            domain = domains[idx]
            try:
                content, err = future.result()
            except Exception as e:
                content, err = None, str(e)
            if err:
                errors[domain] = err
                for line in lines:
                    results[line][idx] = "Error"
            else:
                for line in lines:
                    found = check_line_in_content(content, line_elements[line], case_sensitives[line])
                    results[line][idx] = "Yes" if found else "No"
            progress_bar.progress(processed / len(domains))
    st.success(f"Done in {time.time()-start_time:.2f}s")
    df = pd.DataFrame(results)
    st.dataframe(df)
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button("💾 Download Results", data=csv_data, file_name="ads_txt_results.csv", mime="text/csv")

with st.expander("🗄️ View raw data.json"):
    st.json(data)
