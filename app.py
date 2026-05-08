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
                elements = [e.strip() for e in line.split(",")]
            else:
                elements = [line]

            # Store ALL elements — field_limit applied at match time only
            line_elements[line] = elements

            case_sensitives[line] = {}

            st.markdown(f"**Line: `{line}`**")

            display_elements = elements[:field_limit]
            cols = st.columns(len(display_elements))

            for i, element in enumerate(display_elements):
                with cols[i]:
                    unique_key = f"case_{line}_{element}_{i}"
                    case_sensitives[line][f"{element}_{i}"] = st.checkbox(
                        element,
                        value=select_all_case,
                        key=unique_key
                    )

        # ---- Live debug preview of parsed elements ----
        st.markdown("---")
        st.markdown("**🔬 Parsed Search Elements (live)**")
        for line, elems in line_elements.items():
            sliced = elems[:field_limit]
            st.code(
                f"Line     : {repr(line)}\n"
                f"All elems: {elems}\n"
                f"After field_limit={field_limit}: {sliced}",
                language="text"
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
def fetch_with_retry(domain, max_retries=2, timeout=10):
    """
    Fetch ads.txt using streaming to prevent truncation of large files.
    Tries https/http and with/without www prefix.
    """

    base_domains = [domain]
    if not domain.startswith("www."):
        base_domains.append(f"www.{domain}")

    urls = []
    for d in base_domains:
        urls.append(f"https://{d}/{file_type}")
        urls.append(f"http://{d}/{file_type}")

    last_error = None

    for url in urls:

        for attempt in range(max_retries):

            try:

                time.sleep(random.uniform(0.05, 0.2))

                random_ua = random.choice(USER_AGENTS)

                headers = {
                    "User-Agent": random_ua,
                    # identity = no compression, prevents partial decode truncation
                    "Accept-Encoding": "identity",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                }

                # stream=True: read the full response without a size cap
                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=headers,
                    stream=True
                )

                if response.status_code == 200:

                    try:
                        # Read full content via streaming to avoid truncation
                        raw_bytes = b""
                        for chunk in response.iter_content(chunk_size=8192):
                            raw_bytes += chunk

                        # Detect encoding
                        encoding = response.encoding or "utf-8"
                        content = raw_bytes.decode(encoding, errors="replace")

                    except Exception:
                        last_error = "Encoding Error"
                        continue

                    if not content.strip():
                        last_error = "Empty Response"
                        continue

                    # Normalize whitespace variants
                    content = (
                        content
                        .replace("\u00a0", " ")
                        .replace("\t", " ")
                        .replace("\r", "")
                    )

                    lower_content = content.lower()

                    # Reject HTML/WAF pages
                    if (
                        "<html" in lower_content or
                        "<!doctype html" in lower_content or
                        "<head>" in lower_content or
                        "<body>" in lower_content
                    ):
                        last_error = "HTML/WAF Response"
                        continue

                    return content, None

                elif response.status_code == 403:
                    last_error = "403 Blocked (WAF)"

                elif response.status_code == 404:
                    last_error = "404 Not Found"

                elif response.status_code == 429:
                    last_error = "429 Rate Limited"

                elif response.status_code >= 500:
                    last_error = f"{response.status_code} Server Error"

                else:
                    last_error = f"HTTP {response.status_code}"

            except requests.exceptions.Timeout:
                last_error = "Timeout"

            except requests.exceptions.ConnectionError:
                last_error = "Connection Failed"

            except requests.exceptions.TooManyRedirects:
                last_error = "Redirect Loop"

            except Exception as e:
                last_error = str(e)

    return None, last_error


# ---------------- Strip Comment ----------------
def strip_comment(raw_line):
    """Strip inline # comments — handles with or without space before #"""
    return raw_line.split("#")[0].strip()


# ---------------- Matching Function ----------------
def check_line_in_content(content, all_line_elements, case_sensitives_line, field_limit):

    if not content:
        return False, []

    # Apply field_limit HERE — not at UI parse time
    line_elements = all_line_elements[:field_limit]

    debug_info = []

    cleaned_lines = []

    for raw_line in content.splitlines():
        stripped = strip_comment(raw_line.strip())
        if stripped:
            cleaned_lines.append(stripped)

    for c_line in cleaned_lines:

        c_line = re.sub(r'\s+', ' ', c_line.strip())
        content_parts = [p.strip() for p in c_line.split(",")]

        # ==================================================
        # SIMPLE SEARCH MODE
        # ==================================================
        if len(line_elements) == 1:

            search_element = re.sub(r'\s+', ' ', line_elements[0].strip())

            if search_element.lower() == "<any>":
                return True, debug_info

            is_case_sensitive = case_sensitives_line.get(f"{search_element}_0", False)

            if is_case_sensitive:
                if search_element in c_line:
                    return True, debug_info
            else:
                if search_element.lower() in c_line.lower():
                    return True, debug_info

        # ==================================================
        # FIELD MATCH MODE
        # ==================================================
        else:

            if len(content_parts) < len(line_elements):
                continue

            matched = True
            field_debug = []

            for i, search_element in enumerate(line_elements):

                se = re.sub(r'\s+', ' ', search_element.strip())
                ce = re.sub(r'\s+', ' ', content_parts[i].strip())

                if se.lower() == "<any>":
                    field_debug.append(f"Field {i}: {repr(se)} == <any> ✅")
                    continue

                is_case_sensitive = case_sensitives_line.get(f"{search_element}_{i}", False)

                if is_case_sensitive:
                    eq = (se == ce)
                else:
                    eq = (se.lower() == ce.lower())

                field_debug.append(
                    f"Field {i}: search={repr(se)} | content={repr(ce)} | {'✅' if eq else '❌'}"
                )

                if not eq:
                    matched = False
                    break

            if matched:
                debug_info.append(f"MATCH on: {c_line}\n  " + "\n  ".join(field_debug))
                return True, debug_info
            else:
                # Log near-misses where first field matched
                if field_debug and "✅" in field_debug[0]:
                    debug_info.append(f"Near-miss: {c_line}\n  " + "\n  ".join(field_debug))

    return False, debug_info


# ---------------- Single Domain Debug Tool ----------------
st.markdown("---")
st.header("🔬 Debug Single Domain")
st.caption("Paste one domain and one search line to see exactly what is happening")

debug_domain = st.text_input(
    "Domain to debug",
    placeholder="euronews.com"
)
debug_line = st.text_input(
    "Search line to debug",
    placeholder="nativo.com, 6047, RESELLER"
)

if st.button("🔍 Run Debug") and debug_domain and debug_line:

    with st.spinner("Fetching..."):
        content, err = fetch_with_retry(debug_domain.strip())

    if err:
        st.error(f"Fetch failed: {err}")

    else:
        total_lines = len(content.splitlines())
        st.success(f"✅ Fetched — {total_lines} total lines, {len(content)} chars")

        # Show raw lines containing the first field keyword
        keyword = debug_line.split(",")[0].strip().lower()
        matching_raw = [l for l in content.splitlines() if keyword in l.lower()]

        st.markdown(f"**Raw lines in file containing `{keyword}`:**")
        if matching_raw:
            for l in matching_raw:
                st.code(repr(l), language="text")
        else:
            st.warning(
                f"❌ No lines containing '{keyword}' found in the fetched content.\n\n"
                f"The file only has {total_lines} lines — the real file may have more. "
                f"This usually means the server returned a truncated or cached version."
            )

        # Parse and show search elements
        if "," in debug_line:
            d_elements = [e.strip() for e in debug_line.split(",")]
        else:
            d_elements = [debug_line.strip()]

        st.markdown(f"**Parsed search elements:** `{d_elements}`")
        st.markdown(f"**field_limit:** `{field_limit}`")
        st.markdown(f"**Elements used for matching:** `{d_elements[:field_limit]}`")

        # Run match with debug
        dummy_case = {f"{e}_{i}": False for i, e in enumerate(d_elements)}
        found, debug_info = check_line_in_content(content, d_elements, dummy_case, field_limit)

        if found:
            st.success("✅ Result: YES — Match found")
        else:
            st.error("❌ Result: NO — No match")

        if debug_info:
            st.markdown("**Debug trace (matches + near-misses):**")
            for info in debug_info:
                st.code(info, language="text")
        else:
            st.warning("No near-misses either — the keyword does not exist in the fetched content.")

        # Show first 20 and last 20 lines to spot truncation
        all_lines = content.splitlines()
        with st.expander("📄 First 20 lines of fetched content"):
            for l in all_lines[:20]:
                st.text(repr(l))
        with st.expander("📄 Last 20 lines of fetched content"):
            for l in all_lines[-20:]:
                st.text(repr(l))


# ---------------- Main Checking ----------------
st.markdown("---")
if st.button("🚀 Start Checking", disabled=not (domains and lines)):

    start_time = time.time()

    results = {"Page": domains}

    for line in lines:
        results[line] = [""] * len(domains)

    errors = {}

    progress_bar = st.progress(0)
    status_text  = st.empty()

    with ThreadPoolExecutor(max_workers=15) as executor:

        future_to_index = {
            executor.submit(fetch_with_retry, domain): idx
            for idx, domain in enumerate(domains)
        }

        for processed, future in enumerate(as_completed(future_to_index), 1):

            idx    = future_to_index[future]
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
                    found, _ = check_line_in_content(
                        content,
                        line_elements[line],
                        case_sensitives[line],
                        field_limit
                    )
                    results[line][idx] = "Yes" if found else "No"

            progress_bar.progress(processed / len(domains))
            status_text.text(f"Processed {processed}/{len(domains)} domains...")

    end_time = time.time()

    st.success(f"🎉 Done! Time taken: {end_time - start_time:.2f} seconds")

    # ---------------- Results ----------------
    st.subheader("📊 Results")

    df = pd.DataFrame(results)

    st.dataframe(df, use_container_width=True, height=400)

    csv_data = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "💾 Download Results as CSV",
        data=csv_data,
        file_name="ads_txt_check_results.csv",
        mime="text/csv"
    )

    # ---------------- Errors ----------------
    if errors:

        st.subheader("⚠️ Errors")

        error_df = pd.DataFrame({
            "Page":  list(errors.keys()),
            "Error": list(errors.values())
        })

        st.dataframe(error_df, use_container_width=True)
