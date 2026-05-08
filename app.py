import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re
import random

# ---------------- Page Setup ----------------
st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("Ads.txt Validator")

# ---------------- Input Tabs ----------------
tab1, tab2 = st.tabs(["📋 Paste Domains", "📂 Upload Domains File"])

domains = []

with tab1:
    st.header("Input Domains")

    domain_input = st.text_area(
        "Paste domains (one per line)",
        height=200
    )

    st.caption("Use 100 Domains per search for accurate and faster result")

    if domain_input:
        domains = [
            d.strip()
            for d in domain_input.splitlines()
            if d.strip()
        ]

with tab2:

    st.header("Upload File")

    uploaded_file = st.file_uploader(
        "Upload CSV/TXT file with domains",
        type=["csv", "txt"]
    )

    if uploaded_file:

        stringio = StringIO(
            uploaded_file.getvalue().decode("utf-8")
        )

        uploaded_domains = [
            line.strip()
            for line in stringio.readlines()
            if line.strip()
        ]

        domains.extend(uploaded_domains)

# ---------------- Deduplicate ----------------
domains = list(dict.fromkeys(domains))

if domains:
    st.info(f"✅ {len(domains)} unique domains loaded.")

# ---------------- Search Lines ----------------
st.header("🔍 Search Lines")

line_input = st.text_area(
    "Paste search lines (CSV format or single word/number, one per line)",
    height=200,
    placeholder="""pubmatic.com
xapads.com,223557,RESELLER
google.com,<any>,DIRECT,<any>"""
)

st.info(
    "💡 Wildcard Support:\n\n"
    "`<any>` matches any value in that field.\n\n"
    "Examples:\n"
    "`google.com,<any>,DIRECT,<any>`\n"
    "`pubmatic.com,<any>,RESELLER`"
)

# ---------------- File Type ----------------
file_type = st.selectbox(
    "Select file type",
    ["ads.txt", "app-ads.txt"]
)

# ---------------- Field Limit ----------------
field_limit = st.selectbox(
    "Select number of fields to check",
    [1, 2, 3, 4],
    index=1
)

# ---------------- Process Lines ----------------
lines = [
    l.strip()
    for l in line_input.splitlines()
    if l.strip()
]

case_sensitives = {}
line_elements = {}

if lines:

    with st.expander("⚙ Line Settings", expanded=True):

        select_all_case = st.checkbox(
            "Select all elements as case-sensitive",
            value=False
        )

        for line in lines:

            if "," in line:
                elements = [
                    e.strip()
                    for e in line.split(",")
                ]
            else:
                elements = [line]

            # IMPORTANT
            line_elements[line] = elements[:field_limit]

            case_sensitives[line] = {}

            st.markdown(f"**Line: {line}**")

            cols = st.columns(len(line_elements[line]))

            for i, element in enumerate(line_elements[line]):

                with cols[i]:

                    unique_key = f"case_{line}_{element}_{i}"

                    case_sensitives[line][f"{element}_{i}"] = st.checkbox(
                        element,
                        value=select_all_case,
                        key=unique_key
                    )

# ---------------- User Agent Pool ----------------
USER_AGENTS = [

    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),

    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),

    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
        "Gecko/20100101 Firefox/140.0"
    ),

    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Safari/605.1.15"
    )
]

# ---------------- Session ----------------
session = requests.Session()

# ---------------- Fetch Function ----------------
def fetch_with_retry(domain, max_retries=2, timeout=5):

    urls = [
        f"https://{domain}/{file_type}",
        f"http://{domain}/{file_type}"
    ]

    last_error = None

    for url in urls:

        for attempt in range(max_retries):

            try:

                # small randomized delay
                time.sleep(random.uniform(0.05, 0.2))

                # rotate UA
                random_ua = random.choice(USER_AGENTS)

                headers = {
                    "User-Agent": random_ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Cache-Control": "max-age=0",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }

                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=headers
                )

                if response.status_code == 200:
                    return response.text, None

                else:
                    last_error = f"HTTP {response.status_code}"

            except requests.exceptions.SSLError:

                try:

                    response = session.get(
                        url,
                        timeout=timeout,
                        allow_redirects=True,
                        verify=False,
                        headers=headers
                    )

                    if response.status_code == 200:
                        return response.text, None

                    else:
                        last_error = f"HTTP {response.status_code}"

                except Exception as e:
                    last_error = str(e)

            except Exception as e:
                last_error = str(e)

    return None, last_error

# ---------------- Matching Function ----------------
def check_line_in_content(content, line_elements, case_sensitives_line):

    if not content:
        return False

    cleaned_lines = []

    for line in content.splitlines():

        line = re.split(r'\s*#', line.strip())[0].strip()

        if line:
            cleaned_lines.append(line)

    # ---------------- LOOP ADS.TXT LINES ----------------
    for c_line in cleaned_lines:

        content_parts = [
            p.strip()
            for p in c_line.split(",")
        ]

        # ==================================================
        # SIMPLE SEARCH MODE
        # ==================================================
        if len(line_elements) == 1:

            search_element = line_elements[0].strip()

            # wildcard only
            if search_element.lower() == "<any>":
                return True

            is_case_sensitive = case_sensitives_line.get(
                f"{search_element}_0",
                False
            )

            if is_case_sensitive:

                if search_element in c_line:
                    return True

            else:

                if search_element.lower() in c_line.lower():
                    return True

        # ==================================================
        # FIELD MATCH MODE
        # ==================================================
        else:

            # fewer fields than required
            if len(content_parts) < len(line_elements):
                continue

            matched = True

            for i, search_element in enumerate(line_elements):

                search_element = search_element.strip()

                content_element = content_parts[i].strip()

                # wildcard
                if search_element.lower() == "<any>":
                    continue

                is_case_sensitive = case_sensitives_line.get(
                    f"{search_element}_{i}",
                    False
                )

                # case sensitive
                if is_case_sensitive:

                    if search_element != content_element:
                        matched = False
                        break

                # case insensitive
                else:

                    if search_element.lower() != content_element.lower():
                        matched = False
                        break

            if matched:
                return True

    return False

# ---------------- Main Checking ----------------
if st.button("🚀 Start Checking", disabled=not (domains and lines)):

    start_time = time.time()

    results = {"Page": domains}

    for line in lines:
        results[line] = [""] * len(domains)

    errors = {}

    progress_bar = st.progress(0)

    status_text = st.empty()

    # optimized thread count
    with ThreadPoolExecutor(max_workers=15) as executor:

        future_to_index = {
            executor.submit(fetch_with_retry, domain): idx
            for idx, domain in enumerate(domains)
        }

        for processed, future in enumerate(
            as_completed(future_to_index),
            1
        ):

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

                    found = check_line_in_content(
                        content,
                        line_elements[line],
                        case_sensitives[line]
                    )

                    results[line][idx] = (
                        "Yes" if found else "No"
                    )

            progress_bar.progress(
                processed / len(domains)
            )

            status_text.text(
                f"Processed {processed}/{len(domains)} domains..."
            )

    end_time = time.time()

    st.success(
        f"🎉 Checking complete! "
        f"Time taken: {end_time - start_time:.2f} seconds"
    )

    # ---------------- Results ----------------
    st.subheader("📊 Results")

    df = pd.DataFrame(results)

    st.dataframe(
        df,
        use_container_width=True,
        height=400
    )

    csv_data = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "💾 Download Results as CSV",
        data=csv_data,
        file_name="ads_txt_check_results.csv",
        mime="text/csv"
    )

    # ---------------- Errors ----------------
    if errors:

        st.subheader("Errors")

        error_df = pd.DataFrame({
            "Page": list(errors.keys()),
            "Error": list(errors.values())
        })

        st.dataframe(
            error_df,
            use_container_width=True
        )
