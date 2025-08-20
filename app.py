import streamlit as st
import requests
import pandas as pd
import io

# Function to fetch and check the ads.txt/app-ads.txt file
def check_ads_file(domain, lines_to_check, file_type):
    """Fetches the ads/app-ads file and checks for specified lines."""
    
    # Standardize the domain URL
    if not domain.startswith('http'):
        url = f"https://{domain}/{file_type}"
    else:
        url = f"{domain}/{file_type}"
    
    found_lines = {}
    
    # Fetch the file content
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        
        file_content = response.text
        
        # Check for each line
        for line_key, line_parts in lines_to_check.items():
            found = "No"
            # Flexible matching logic (match first two or all three parts)
            for file_line in file_content.splitlines():
                if not file_line.strip() or file_line.startswith('#'):
                    continue
                
                # Normalize line for comparison
                normalized_file_line = ' '.join(file_line.strip().split()).lower()
                
                # Check based on user's input parts
                if len(line_parts) >= 3 and len(normalized_file_line.split()) >= 3:
                    if normalized_file_line.startswith(f"{line_parts[0]} {line_parts[1]} {line_parts[2]}"):
                        found = "Yes"
                        break
                elif len(line_parts) >= 2:
                    if normalized_file_line.startswith(f"{line_parts[0]} {line_parts[1]}"):
                        found = "Yes"
                        break
            found_lines[line_key] = found
            
    except requests.exceptions.RequestException as e:
        # Handle network errors, timeouts, and non-200 responses
        st.error(f"Error fetching from {url}: {e}")
        for line_key in lines_to_check.keys():
            found_lines[line_key] = "Error"

    return found_lines

# --- Streamlit App UI ---
st.title("Ads.txt / App-Ads.txt Checker")
st.markdown("Use this app to validate `ads.txt` or `app-ads.txt` files across multiple domains.")

# --- Inputs ---
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
        # Parse inputs
        domains = [d.strip() for d in domains_input.splitlines() if d.strip()]
        lines = [l.strip() for l in lines_input.splitlines() if l.strip()]
        
        if not domains or not lines:
            st.warning("The domains or lines list is empty after parsing. Please check your input.")
        else:
            # Parse lines to check into a structured dictionary
            parsed_lines = {}
            for i, line in enumerate(lines):
                # Split by comma or space and clean parts
                parts = [p.strip().lower() for p in line.replace(',', ' ').split() if p.strip()]
                if len(parts) >= 2:
                    parsed_lines[f"Line {i+1}: {' '.join(parts)}"] = parts
                else:
                    st.error(f"Skipping malformed line: '{line}'. A line must have at least two parts (domain, ID).")
            
            if not parsed_lines:
                st.error("No valid lines were found to check. Please re-enter the lines.")
            else:
                st.subheader("Results")
                
                # Create a DataFrame to hold results
                results_df = pd.DataFrame(index=domains)
                for line_name in parsed_lines.keys():
                    results_df[line_name] = "Pending"
                    
                progress_bar = st.progress(0)
                
                # Process each domain and update the DataFrame
                for i, domain in enumerate(domains):
                    domain_results = check_ads_file(domain, parsed_lines, file_type)
                    
                    for line_name, status in domain_results.items():
                        results_df.loc[domain, line_name] = status
                    
                    progress_bar.progress((i + 1) / len(domains))
                    
                st.dataframe(results_df)

                # --- Output CSV ---
                csv_buffer = io.StringIO()
                results_df.to_csv(csv_buffer)
                csv_bytes = csv_buffer.getvalue().encode('utf-8')
                
                st.download_button(
                    label="Download Results as CSV",
                    data=csv_bytes,
                    file_name=f"ads_txt_check_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
