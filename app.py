import streamlit as st
import requests
import pandas as pd
import io

# Function to fetch and check the ads.txt/app-ads.txt file
def check_ads_file(domain, lines_to_check, file_type):
    """
    Fetches the ads/app-ads file using a User-Agent and provides detailed error handling.
    """
    
    # Use a standard browser User-Agent to avoid 403 Forbidden errors
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Standardize the domain URL, prioritizing HTTPS
    if not domain.startswith('http'):
        url = f"https://{domain}/{file_type}"
    else:
        url = f"{domain}/{file_type}"
    
    found_lines = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check HTTP status code for specific errors
        if response.status_code == 200:
            file_content = response.text
            
            # Perform the content check
            for line_key, line_parts in lines_to_check.items():
                found = "No"
                for file_line in file_content.splitlines():
                    if not file_line.strip() or file_line.startswith('#'):
                        continue
                    
                    normalized_file_line = ' '.join(file_line.strip().split()).lower()
                    
                    if len(line_parts) >= 3 and len(normalized_file_line.split()) >= 3:
                        if normalized_file_line.startswith(f"{line_parts[0]} {line_parts[1]} {line_parts[2]}"):
                            found = "Yes"
                            break
                    elif len(line_parts) >= 2:
                        if normalized_file_line.startswith(f"{line_parts[0]} {line_parts[1]}"):
                            found = "Yes"
                            break
                found_lines[line_key] = found
        
        elif response.status_code == 404:
            # Handle 404 Not Found error
            for line_key in lines_to_check.keys():
                found_lines[line_key] = "404 Not Found"
        
        elif response.status_code == 403:
            # Handle 403 Forbidden error (often a bot block)
            for line_key in lines_to_check.keys():
                found_lines[line_key] = "403 Forbidden"
        
        else:
            # Handle any other HTTP errors
            for line_key in lines_to_check.keys():
                found_lines[line_key] = f"HTTP Error {response.status_code}"
            
    except requests.exceptions.Timeout:
        # Handle timeout error
        for line_key in lines_to_check.keys():
            found_lines[line_key] = "Request Timeout"
            
    except requests.exceptions.ConnectionError:
        # Handle DNS errors or other connection issues
        for line_key in lines_to_check.keys():
            found_lines[line_key] = "Connection Error"
            
    except requests.exceptions.RequestException as e:
        # Catch-all for any other request-related errors
        st.error(f"An unexpected error occurred for {url}: {e}")
        for line_key in lines_to_check.keys():
            found_lines[line_key] = "Unknown Error"

    return found_lines

# --- Streamlit App UI ---
st.title("Ads.txt / App-Ads.txt Checker")
st.markdown("This tool checks for `ads.txt` or `app-ads.txt` files and their specified lines across multiple domains. It uses a **User-Agent** to prevent being blocked.")

st.markdown("---")

st.subheader("1. Domains List")
st.info("Paste one domain per line (e.g., `google.com`, `nytimes.com`).")
domains_input = st.text_area("Domains to check", height=150, placeholder="Enter domains here...")
st.markdown("---")

st.subheader("2. Lines to Check")
st.info("Paste the lines to check. The app will automatically split them into parts.")
lines_input = st.text_area("Lines to check", height=150, placeholder="Example: `google.com, pub-1234567890, DIRECT`\n`app-ads.com, 98765, RESELLER`")
st.markdown("---")

st.subheader("3. Select File Type")
file_type = st.radio("Choose the file to check", ("ads.txt", "app-ads.txt"))
st.markdown("---")

# --- App Logic ---
if st.button("Run Check"):
    if not domains_input or not lines_input:
        st.warning("Please enter both domains and lines to check.")
    else:
        domains = [d.strip() for d in domains_input.splitlines() if d.strip()]
        lines = [l.strip() for l in lines_input.splitlines() if l.strip()]
        
        if not domains or not lines:
            st.warning("The domains or lines list is empty after parsing. Please check your input.")
        else:
            parsed_lines = {}
            for i, line in enumerate(lines):
                parts = [p.strip().lower() for p in line.replace(',', ' ').split() if p.strip()]
                if len(parts) >= 2:
                    parsed_lines[f"Line {i+1}: {' '.join(parts)}"] = parts
                else:
                    st.error(f"Skipping malformed line: '{line}'. A line must have at least two parts (domain, ID).")
            
            if not parsed_lines:
                st.error("No valid lines were found to check. Please re-enter the lines.")
            else:
                st.subheader("Results")
                
                results_df = pd.DataFrame(index=domains)
                for line_name in parsed_lines.keys():
                    results_df[line_name] = "Pending"
                    
                progress_bar = st.progress(0)
                
                for i, domain in enumerate(domains):
                    domain_results = check_ads_file(domain, parsed_lines, file_type)
                    
                    for line_name, status in domain_results.items():
                        results_df.loc[domain, line_name] = status
                    
                    progress_bar.progress((i + 1) / len(domains))
                    
                st.dataframe(results_df)

                csv_buffer = io.StringIO()
                results_df.to_csv(csv_buffer)
                csv_bytes = csv_buffer.getvalue().encode('utf-8')
                
                st.download_button(
                    label="Download Results as CSV",
                    data=csv_bytes,
                    file_name=f"ads_txt_check_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
