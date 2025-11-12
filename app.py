# full_streamlit_ads_checker.py
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
    # Requires secrets: GITHUB_TOKEN and GITHUB_REPO (owner/repo)
    token = st.secrets.get("GITHUB_TOKEN") if st.secrets else None
    repo = st.secrets.get("GITHUB_REPO") if st.secrets else None
    branch = st.secrets.get("GITHUB_BRANCH") if st.secrets and "GITHUB_BRANCH" in st.secrets else DEFAULT_BRANCH

    if not token or not repo:
        return False, "GitHub token or repo not configured in Streamlit secrets."

    owner_repo = repo.strip()
    path = DATA_FILE

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    api_base = "https://api.github.com"

    # fetch current file to get sha (if exists)
    get_url = f"{api_base}/repos/{owner_repo}/contents/{path}?ref={branch}"
    r = requests.get(get_url, headers=headers)
    file_sha = None
    if r.status_code == 200:
        file_sha = r.json().get("sha")

    # prepare content
    content_bytes = json.dumps(data, indent=2).encode("utf-8")
    content_b64 = base64.b64encode(content_bytes).decode("utf-8")

    put_url = f"{api_base}/repos/{owner_repo}/contents/{path}"
    payload = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if file_sha:
        payload["sha"] = file_sha

    put = requests.put(put_url, headers=headers, json=payload)
    if put.status_code in (200, 201):
        return True, "Committed to GitHub."
    else:
        return False, f"GitHub API error {put.status_code}: {put.text}"

# ---------------- Load stored data ----------------
data = load_data()
if "domains" not in data:
    data["domains"] = {}
if "snapshots" not in data:
    data["snapshots"] = {}

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

# Deduplicate and preserve order
domains_input_from_ui = list(dict.fromkeys(domains_input_from_ui))
if domains_input_from_ui:
    st.info(f"✅ {len(domains_input_from_ui)} unique domains loaded into ad-hoc check queue.")

# ---------------- Search Lines (ad-hoc checking) ----------------
st.header("🔍 Ad-hoc Search Lines (for Start Checking)")
line_input = st.text_area("Paste search lines (CSV format or single word/number, one per line). These are used by the 'Start Checking' button (ad-hoc).", height=200)

# ---------------- File type selection (ad-hoc) ----------------
file_type = st.selectbox("Select file type for ad-hoc check", ["ads.txt", "app-ads.txt"])

# ---------------- Field Limit Selection (ad-hoc) ----------------
field_limit = st.selectbox(
    "Select number of fields to check (for CSV-style lines in ad-hoc mode)",
    [1, 2, 3, 4],
    index=1  # default = 2
)

# ---------------- Process ad-hoc Lines ----------------
lines = [l.strip() for l in line_input.splitlines() if l.strip()]
case_sensitives = {}
line_elements = {}

if lines:
    with st.expander("⚙ Ad-hoc Line Settings (case sensitivity)", expanded=True):
        select_all_case = st.checkbox("Select all elements as case-sensitive (ad-hoc)", value=False)
        for line in lines:
            if "," in line:
                elements = [e.strip() for e in line.split(',') if e.strip()]
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

proxy_input = st.sidebar.text_input(
    "Proxy (optional)",
    placeholder="http://user:pass@host:port OR http://host:port"
)
proxies = {"http": proxy_input, "https": proxy_input} if proxy_input else None

ua_choice = st.sidebar.radio(
    "User-Agent Mode",
    ["Live Browser UA", "AdsBot-Google UA"],
    index=0
)

# ---------------- User-Agent ----------------
if ua_choice == "Live Browser UA":
    LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
else:
    LIVE_UA = "Mozilla/5.0 (compatible; AdsBot-Google; +http://www.google.com/adsbot.html)"

st.sidebar.write(f"🟢 Using User-Agent: {LIVE_UA}")

# ---------------- Global Session ----------------
session = requests.Session()
session.headers.update({
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,/;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': LIVE_UA
})
if proxies:
    session.proxies.update(proxies)

# ---------------- Fetch with retry (SSL handling) ----------------
def fetch_with_retry(domain, file_type_local, session_local=session, max_retries=2, timeout=8):
    urls = [f"https://{domain}/{file_type_local}", f"http://{domain}/{file_type_local}"]
    last_error = None
    for url in urls:
        for attempt in range(max_retries):
            try:
                response = session_local.get(url, timeout=timeout, allow_redirects=True)
                if response.status_code == 200:
                    return response.text, None
                else:
                    last_error = f"HTTP {response.status_code}"
            except requests.exceptions.SSLError:
                try:
                    response = session_local.get(url, timeout=timeout, allow_redirects=True, verify=False)
                    if response.status_code == 200:
                        return response.text, None
                    else:
                        last_error = f"HTTP {response.status_code}"
                except Exception as e:
                    last_error = str(e)
            except Exception as e:
                last_error = str(e)
    return None, last_error

# ---------------- Check line content (re-usable) ----------------
def check_line_in_content(content, line_elements_local, case_sensitives_line):
    if not content:
        return False
    content_lines = content.splitlines()
    cleaned_lines = [
        re.split(r'\s*#', line.strip())[0].strip()
        for line in content_lines
        if line.strip() and not line.strip().startswith('#')
    ]

    for c_line in cleaned_lines:
        content_parts = [e.strip() for e in c_line.split(',')]

        # Single-element searches (not CSV style)
        if len(line_elements_local) == 1 and "," not in line_elements_local[0]:
            element_to_find = line_elements_local[0]
            if case_sensitives_line.get(element_to_find, False):
                if element_to_find in c_line:
                    return True
            else:
                if element_to_find.lower() in c_line.lower():
                    return True
        else:
            # CSV-style matching: match position-wise (respect case-sensitivity per element)
            all_match = True
            for i, element_to_find in enumerate(line_elements_local):
                if i >= len(content_parts):
                    all_match = False
                    break
                content_element = content_parts[i]
                if case_sensitives_line.get(element_to_find, False):
                    if element_to_find != content_element:
                        all_match = False
                        break
                else:
                    if element_to_find.lower() != content_element.lower():
                        all_match = False
                        break
            if all_match:
                return True
    return False

# ---------------- Data Manager (Add/Edit/Delete tracked domains) ----------------
st.sidebar.markdown("---")
st.sidebar.header("🔧 Data Manager (Persistent Tracker)")

with st.sidebar.form("domain_form", clear_on_submit=False):
   dm_domains = st.text_area(
    "Domains to track (one per line)",
    height=120,
    placeholder="hola.com\nsharechat.com\nm.daily"
)
   dm_type = st.selectbox("File type", ["ads.txt", "app-ads.txt"])
   dm_lines = st.text_area(
    "Lines to monitor (one per line)",
    height=120,
    placeholder="pubmatic.com\ngoogle.com"
)
   submitted = st.form_submit_button("Add / Update Domain(s)")
   delete_domain = st.form_submit_button("Delete Domain(s)")


if submitted and dm_domain:
    lines_list = [l.strip() for l in dm_lines.splitlines() if l.strip()]
    data["domains"][dm_domain.strip()] = {"type": dm_type, "lines": lines_list}
    save_local_data(data)
    # attempt GitHub commit if secrets present
    if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
        ok, msg = github_commit_datafile(data, commit_message=f"Streamlit: add/update domain {dm_domain.strip()}")
        if ok:
            st.sidebar.success(f"Saved and committed to GitHub: {dm_domain.strip()}")
        else:
            st.sidebar.warning(f"Saved locally but GitHub commit failed: {msg}")
    else:
        st.sidebar.success(f"Saved locally: {dm_domain.strip()}")

if delete_domain and dm_domain:
    if dm_domain.strip() in data["domains"]:
        data["domains"].pop(dm_domain.strip(), None)
        save_local_data(data)
        if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
            ok, msg = github_commit_datafile(data, commit_message=f"Streamlit: delete domain {dm_domain.strip()}")
            if ok:
                st.sidebar.success(f"Deleted and committed to GitHub: {dm_domain.strip()}")
            else:
                st.sidebar.warning(f"Deleted locally but GitHub commit failed: {msg}")
        else:
            st.sidebar.success(f"Deleted locally: {dm_domain.strip()}")
    else:
        st.sidebar.warning("Domain not found in tracked list.")

# Show tracked domains
st.sidebar.markdown("**Tracked domains:**")
if data["domains"]:
    for d, info in data["domains"].items():
        st.sidebar.markdown(f"- `{d}` ({info.get('type','ads.txt')}) — {len(info.get('lines',[]))} line(s)")
else:
    st.sidebar.info("No domains tracked yet. Add domains here to start daily reports.")

st.sidebar.markdown("---")
st.sidebar.markdown("**Optional GitHub persistence**\n\nAdd the following keys to Streamlit secrets if you want persistent storage across restarts:\n- `GITHUB_TOKEN` (personal access token with `repo` scope)\n- `GITHUB_REPO` (owner/repo e.g. `youruser/yourrepo`)\n- `GITHUB_BRANCH` (optional, default `main`)")

# ---------------- Main: Generate Today's Report (for tracked domains) ----------------
st.header("📅 Daily Report (for tracked domains)")

col1, col2 = st.columns([1, 2])
with col1:
    if st.button("🗓️ Generate Today's Report (tracked domains)"):
        if not data["domains"]:
            st.warning("No domains are being tracked. Add domains in the Data Manager (sidebar).")
        else:
            today = datetime.date.today().isoformat()
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            snapshots = {}
            report_rows = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            dom_items = list(data["domains"].items())
            with ThreadPoolExecutor(max_workers=20) as executor:
                future_to_idx = {executor.submit(fetch_with_retry, domain, info["type"]): idx for idx, (domain, info) in enumerate(dom_items)}
                for processed, future in enumerate(as_completed(future_to_idx), 1):
                    idx = future_to_idx[future]
                    domain, info = dom_items[idx]
                    try:
                        content, err = future.result()
                    except Exception as e:
                        content, err = None, str(e)

                    tracked_lines = info.get("lines", [])
                    found_lines = []
                    if err:
                        # treat as none found
                        snapshots[domain] = []
                        report_rows.append({
                            "Domain": domain,
                            "Status": f"Error: {err}",
                            "Added": "-",
                            "Removed": "-",
                            "Unchanged": "-"
                        })
                    else:
                        # for each tracked line check presence
                        for tracked_line in tracked_lines:
                            # support CSV-style or single-term matching by splitting csv if present
                            elements = [e.strip() for e in tracked_line.split(",")] if "," in tracked_line else [tracked_line]
                            # default to case-insensitive for tracked items (you can expand UI later to set per-line case)
                            found = check_line_in_content(content, elements, {tracked_line: False})
                            if found:
                                found_lines.append(tracked_line)
                        snapshots[domain] = found_lines

                        old = set(data["snapshots"].get(yesterday, {}).get(domain, []))
                        new = set(found_lines)
                        added = new - old
                        removed = old - new
                        unchanged = new & old

                        report_rows.append({
                            "Domain": domain,
                            "Status": "OK",
                            "Added": ", ".join(sorted(added)) if added else "-",
                            "Removed": ", ".join(sorted(removed)) if removed else "-",
                            "Unchanged": ", ".join(sorted(unchanged)) if unchanged else "-"
                        })

                    progress_bar.progress(processed / len(dom_items))
                    status_text.text(f"Processed {processed}/{len(dom_items)} domains...")

            # Save snapshot
            data["snapshots"][today] = snapshots
            save_local_data(data)

            # Try GitHub commit for persistence if configured
            gh_msg = ""
            if st.secrets and "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
                ok, msg = github_commit_datafile(data, commit_message=f"Streamlit daily snapshot {today}")
                gh_msg = msg if not ok else "Committed snapshot to GitHub."
            else:
                gh_msg = "GitHub commit not configured; snapshot saved locally (ephemeral on Streamlit Cloud)."

            # Show results
            st.success(f"Daily report generated for {len(report_rows)} domains. {gh_msg}")
            df_report = pd.DataFrame(report_rows).set_index("Domain")
            # color-coded display
            def highlight_changes(val):
                if isinstance(val, str):
                    if val != "-" and "Error" not in val:
                        # mark Added in green, Removed in red when present
                        return ""
                return ""

            st.dataframe(df_report, use_container_width=True, height=450)

            # CSV download
            csv_bytes = df_report.reset_index().to_csv(index=False).encode("utf-8")
            st.download_button("💾 Download Daily Report (CSV)", data=csv_bytes, file_name=f"daily_report_{today}.csv", mime="text/csv")

with col2:
    st.write("This report compares today's found lines vs yesterday's snapshot and lists Added / Removed / Unchanged lines for each tracked domain.")
    st.markdown("- **Add / Update domains** using the sidebar Data Manager.")
    st.markdown("- **Snapshots** are stored in `data.json` with date keys (ISO format).")
    st.markdown("- To make snapshots persistent across Streamlit restarts, add `GITHUB_TOKEN` and `GITHUB_REPO` to Streamlit secrets for automatic commits.")

# ---------------- Ad-hoc Start Checking (preserve your original main functionality) ----------------
st.markdown("---")
st.header("🚀 Ad-hoc Checking (Start Checking)")

if st.button("Start Checking (ad-hoc)", disabled=not (domains_input_from_ui and lines)):
    domains = domains_input_from_ui
    start_time = time.time()
    results = {"Page": domains}
    for line in lines:
        results[line] = [""] * len(domains)
    errors = {}

    progress_bar = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_index = {executor.submit(fetch_with_retry, domain, file_type): idx for idx, domain in enumerate(domains)}
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
            status_text.text(f"Processed {processed}/{len(domains)} domains...")

    end_time = time.time()
    st.success(f"🎉 Checking complete! Time taken: {end_time - start_time:.2f} seconds")

    st.subheader("📊 Results")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, height=400)

    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button("💾 Download Results as CSV", data=csv_data, file_name="ads_txt_check_results.csv", mime="text/csv")

    if errors:
        st.subheader("Errors")
        error_df = pd.DataFrame({"Page": list(errors.keys()), "Error": list(errors.values())})
        st.dataframe(error_df, use_container_width=True)

# ---------------- Show raw data.json contents (for debugging) ----------------
with st.expander("🗄️ View raw data.json (domains & snapshots)"):
    st.json(data)

