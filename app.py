import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import StringIO
import re
import random
from urllib.parse import urlparse

# ---------------- Page Setup ----------------
st.set_page_config(page_title="Ads.txt / App-ads.txt Bulk Checker", layout="wide")
st.title("Ads.txt Validator")

# ---------------- Pre-compiled Regex Patterns ----------------
# Moving these outside the loops prevents thousands of expensive re-compilations
RE_SCHEME = re.compile(r'^https?://', re.IGNORECASE)
RE_WWW = re.compile(r'^www\.', re.IGNORECASE)
RE_SPACES = re.compile(r'\s+')

# ---------------- Domain Normalizer ----------------
def normalize_domain(raw: str) -> str:
    """
    Accepts any of:
      xyz.com, www.xyz.com, https://xyz.com, https://xyz.com/,
      https://www.xyz.com/, xyz.com/app-ads.txt,
      https://xyz.com/app-ads.txt, http://www.xyz.com/ads.txt
    Returns:
      xyz.com  (no scheme, no www, no path, lowercase, stripped)
    """
    d = raw.strip()
    if not d:
        return ""
    # Remove scheme (http:// or https://)
    d = RE_SCHEME.sub('', d)
    # Remove everything after first slash (path, query, fragment)
    d = d.split("/")[0]
    # Remove port if present
    d = d.split(":")[0]
    # Strip leading www.
    d = RE_WWW.sub('', d)
    # Lowercase and strip whitespace
    d = d.lower().strip()
    return d

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
            normalize_domain(d)
            for d in domain_input.splitlines()
            if d.strip()
        ]
        # Remove empty strings produced by blank lines
        domains = [d for d in domains if d]

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
            normalize_domain(line)
            for line in stringio.readlines()
            if line.strip()
        ]
        # Remove empty strings produced by blank lines
        uploaded_domains = [d for d in uploaded_domains if d]

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
    Fetch ads.txt and let requests handle decompression.
    Optimized URL hierarchy tries clean paths first, implements exponential 
    backoff for 429 rate limiting, and guards against bad redirect chains.
    """
    # Optimized Strategy: HTTPS without www captures >80% of targets natively
    urls = [
        f"https://{domain}/{file_type}",
        f"https://www.{domain}/{file_type}",
        f"http://{domain}/{file_type}",
        f"http://www.{domain}/{file_type}"
    ]

    last_error = None

    for url in urls:
        # Reset attempt loop for each trial URL
        for attempt in range(max_retries):
            try:
                # Artificial thread delay removed for raw performance execution
                random_ua = random.choice(USER_AGENTS)

                headers = {
                    "User-Agent": random_ua,
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                }

                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=headers
                )

                # --- 429 Exponential Backoff and Retry Logic ---
                if response.status_code == 429 and attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                    time.sleep(sleep_time)
                    continue  # Retry the identical URL again

                if response.status_code == 200:
                    try:
                        content = response.text
                    except Exception:
                        last_error = "Encoding Error"
                        break

                    if not content.strip():
                        last_error = "Empty Response"
                        break

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
                        break

                    # Successfully verified and parsed, return content immediately
                    redirected = "Yes" if response.url != url else "No"

                    return (
                        content,
                        None,
                        str(response.status_code),
                        redirected,
                        response.url
                    )
                elif response.status_code == 403:
                    last_error = "403 Blocked (WAF)"
                    break # Skip trying attempts, proceed to next URL option

                elif response.status_code == 404:
                    last_error = "404 Not Found"
                    break

                elif response.status_code == 429:
                    last_error = "429 Rate Limited"
                    break

                elif response.status_code >= 500:
                    last_error = f"{response.status_code} Server Error"
                    break

                else:
                    last_error = f"HTTP {response.status_code}"
                    break

            except requests.exceptions.Timeout:
                last_error = "Timeout"
                break

            except requests.exceptions.ConnectionError:
                last_error = "Connection Failed"
                break

            except requests.exceptions.TooManyRedirects:
                last_error = "Redirect Loop"
                break

            except Exception as e:
                last_error = str(e)
                break

    return (
    None,
    last_error,
    last_error,
    "No",
    ""
)


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
        # Pre-compiled Regex replacement optimization
        c_line = RE_SPACES.sub(' ', c_line.strip())
        content_parts = [p.strip() for p in c_line.split(",")]

        # ==================================================
        # SIMPLE SEARCH MODE
        # ==================================================
        if len(line_elements) == 1:
            search_element = RE_SPACES.sub(' ', line_elements[0].strip())

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
                se = RE_SPACES.sub(' ', search_element.strip())
                ce = RE_SPACES.sub(' ', content_parts[i].strip())

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
                if field_debug and "✅" in field_debug[0]:
                    debug_info.append(f"Near-miss: {c_line}\n  " + "\n  ".join(field_debug))

    return False, debug_info

# ---------------- Main Checking ----------------
st.markdown("---")
if st.button("🚀 Start Checking", disabled=not (domains and lines)):
    start_time = time.time()

    results = {
    "Page": domains,
    "HTTP Status": [""] * len(domains),
    "Redirected": [""] * len(domains),
    "Final URL": [""] * len(domains)
}

    for line in lines:
        results[line] = [""] * len(domains)

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
                content, err, http_status, redirected, final_url = future.result()
                results["HTTP Status"][idx] = http_status
                results["Redirected"][idx] = redirected
                results["Final URL"][idx] = final_url
            except Exception as e:
                content, err = None, str(e)

            if err:
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
