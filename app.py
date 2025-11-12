import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time, json, os, re, datetime, base64
from io import StringIO

st.set_page_config(page_title="Ads.txt / App-Ads.txt Manager", layout="wide")
st.title("🧾 Ads.txt / App-Ads.txt Tracker and Validator")

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
    return {"domains": {"ads.txt": {}, "app-ads.txt": {}}, "snapshots": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def github_commit_datafile(data, commit_message="Update data.json"):
    token = st.secrets.get("GITHUB_TOKEN") if st.secrets else None
    repo = st.secrets.get("GITHUB_REPO") if st.secrets else None
    branch = st.secrets.get("GITHUB_BRANCH", DEFAULT_BRANCH)
    if not token or not repo:
        return False, "GitHub not configured."
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

data = load_data()
data.setdefault("domains", {"ads.txt": {}, "app-ads.txt": {}})
data.setdefault("snapshots", {})

# ---------------- Fetching Utility ----------------
def fetch(domain, ftype, timeout=8):
    urls = [f"https://{domain}/{ftype}", f"http://{domain}/{ftype}"]
    err = None
    for url in urls:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.text, None
        except Exception as e:
            err = str(e)
    return None, err

def check_line_in_content(content, line):
    if not content:
        return False
    for l in content.splitlines():
        if line.lower() in l.lower():
            return True
    return False

# ---------------- Sidebar (Add/Delete Domains) ----------------
st.sidebar.header("🔧 Manage Domains")

tab_ads, tab_app = st.sidebar.tabs(["🧩 ads.txt", "📱 app-ads.txt"])

for ftype, tab in zip(["ads.txt", "app-ads.txt"], [tab_ads, tab_app]):
    with tab:
        st.subheader(f"Manage {ftype}")

        uploaded_file = st.file_uploader(f"Upload domain list for {ftype}", type=["txt", "csv"], key=f"upload_{ftype}")
        domains_text = st.text_area(f"Domains for {ftype}", height=120, placeholder="hola.com\nexample.com")
        if uploaded_file:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            uploaded_domains = [line.strip() for line in stringio.readlines() if line.strip()]
            if domains_text:
                domains_text += "\n" + "\n".join(uploaded_domains)
            else:
                domains_text = "\n".join(uploaded_domains)

        lines_text = st.text_area("Lines to monitor", height=120, placeholder="pubmatic.com\ngoogle.com")
        add_btn = st.button(f"➕ Add/Update {ftype} Domains", key=f"add_{ftype}")
        del_btn = st.button(f"🗑️ Delete {ftype} Domains", key=f"del_{ftype}")

        if add_btn and (domains_text or uploaded_file):
            domains = [d.strip() for d in domains_text.splitlines() if d.strip()]
            lines = [l.strip() for l in lines_text.splitlines() if l.strip()]
            for d in domains:
                data["domains"][ftype][d] = {"lines": lines}
            save_data(data)
            st.success(f"Added/Updated {len(domains)} {ftype} domains.")
            github_commit_datafile(data, f"Added/updated {ftype} domains")

        if del_btn and (domains_text or uploaded_file):
            domains = [d.strip() for d in domains_text.splitlines() if d.strip()]
            removed = 0
            for d in domains:
                if d in data["domains"][ftype]:
                    del data["domains"][ftype][d]
                    removed += 1
            save_data(data)
            st.success(f"Deleted {removed} {ftype} domains.")
            github_commit_datafile(data, f"Deleted {ftype} domains")

# ---------------- Main Tabs for Reports ----------------
main_tab_ads, main_tab_app = st.tabs(["📊 ads.txt Report", "📈 app-ads.txt Report"])

def run_report(ftype):
    if not data["domains"][ftype]:
        st.warning(f"No {ftype} domains tracked.")
        return
    today = datetime.date.today().isoformat()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    snapshots = {}
    report = []
    progress = st.progress(0)
    domains = list(data["domains"][ftype].items())

    with ThreadPoolExecutor(max_workers=20) as exe:
        futures = {exe.submit(fetch, d, ftype): (d, info) for d, info in domains}
        for i, fut in enumerate(as_completed(futures), 1):
            d, info = futures[fut]
            content, err = fut.result()
            found_lines = []
            for l in info["lines"]:
                if check_line_in_content(content, l):
                    found_lines.append(l)
            snapshots[d] = found_lines

            old = set(data["snapshots"].get(yesterday, {}).get(ftype, {}).get(d, []))
            new = set(found_lines)
            added = new - old
            removed = old - new
            unchanged = new & old

            report.append({
                "Domain": d,
                "Added": ", ".join(added) if added else "-",
                "Removed": ", ".join(removed) if removed else "-",
                "Unchanged": ", ".join(unchanged) if unchanged else "-",
                "Error": err or "-"
            })
            progress.progress(i / len(domains))

    data["snapshots"].setdefault(today, {}).setdefault(ftype, snapshots)
    save_data(data)
    github_commit_datafile(data, f"{ftype} snapshot {today}")

    df = pd.DataFrame(report).set_index("Domain")
    st.dataframe(df, use_container_width=True)
    csv = df.reset_index().to_csv(index=False).encode()
    st.download_button("💾 Download CSV", data=csv, file_name=f"{ftype}_report_{today}.csv", mime="text/csv")

# ---------------- Reports for both sections ----------------
with main_tab_ads:
    st.subheader("📊 Daily Report — ads.txt")
    if st.button("Generate ads.txt Report"):
        run_report("ads.txt")

with main_tab_app:
    st.subheader("📈 Daily Report — app-ads.txt")
    if st.button("Generate app-ads.txt Report"):
        run_report("app-ads.txt")

# ---------------- Debug View ----------------
with st.expander("🗄️ View raw data.json"):
    st.json(data)
