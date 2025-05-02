import requests
import json
import time
from urllib.parse import quote
import os # Import os for path joining

# --- Configuration ---
BASE_URL = "https://pxweb.asub.ax:443/PXWeb/api/v1/sv"
SLEEP_TIME = 3 # Increased sleep time in seconds
OUTPUT_DIR = "asub_data" # Directory to save JSON files
# --- End Configuration ---

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch(path):
    """Fetches data from a specific API path."""
    url = f"{BASE_URL}/{path}" if path else BASE_URL
    print(f"\n🔍 Fetching structure: {url}")
    try:
        response = requests.get(url, timeout=30) # Add timeout
        time.sleep(SLEEP_TIME) # Wait AFTER the request
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Optional: Raw response logging for root
        # if path == "":
        #     print("\n📦 RAW ROOT RESPONSE:\n")
        #     print(json.dumps(data, indent=2, ensure_ascii=False))

        return data
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP Error fetching {url}: {http_err}")
        # Log server response if available
        if http_err.response is not None:
             try:
                 print(f"   📄 Server Response: {http_err.response.text[:500]}...") # Print first 500 chars
             except Exception:
                 print("   📄 Server Response: (Could not decode)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ General Error fetching {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error fetching {url}: {e}")
        print(f"   📄 Raw Response: {response.text[:500]}...")
        return None


def summarize_and_get_metadata(path):
    """
    Probes a potential dataset URL, summarizes it, and returns both
    the summary and the fetched metadata (if successful).
    """
    url = f"{BASE_URL}/{quote(path, safe='/')}" # Ensure path is encoded
    try:
        print(f"    🔍 Probing dataset at: {url}")
        response = requests.get(url, timeout=30) # Add timeout
        time.sleep(SLEEP_TIME) # Wait AFTER the request
        response.raise_for_status()
        metadata = response.json()

        # Check if it's a list - indicating a sub-folder, not a table
        if isinstance(metadata, list):
            print(f"    📂 Detected folder (list of items). Not a table.")
            # Return structure indicating it's a sub-tree node
            return {"type": "SUBTREE", "metadata": None}

        # Assume it's a table metadata object
        if not isinstance(metadata, dict) or "variables" not in metadata:
             print(f"    ⚠️ Unexpected structure at {url}. Not a table metadata object.")
             print(f"      Structure type: {type(metadata)}")
             return {"type": "UNKNOWN_STRUCTURE", "metadata": None}

        title = metadata.get("title", "(no title)")
        variables = metadata.get("variables", [])
        print(f"    📊 Dataset: {title} | 📐 Variables: {len(variables)}")

        summary = {
            "title": title,
            "variable_count": len(variables),
            "path": path
        }
        # Optional: Print variable details
        # for var in variables:
        #     code = var.get("code", "?")
        #     values = var.get("values", [])
        #     print(f"      🔸 {code}: {len(values)} values")

        # Return both summary and the metadata to avoid re-fetching
        return {"type": "TABLE", "summary": summary, "metadata": metadata}

    except requests.exceptions.HTTPError as http_err:
        print(f"    ❌ HTTP Error probing {url}: {http_err}")
        if http_err.response is not None:
             try:
                 print(f"       📄 Server Response: {http_err.response.text[:500]}...")
             except Exception:
                 print("       📄 Server Response: (Could not decode)")
        return None # Indicate failure
    except requests.exceptions.RequestException as e:
        print(f"    ❌ General Error probing {url}: {e}")
        return None # Indicate failure
    except json.JSONDecodeError as e:
        print(f"    ❌ JSON Decode Error probing {url}: {e}")
        print(f"       📄 Raw Response: {response.text[:500]}...")
        return None


def download_dataset(path, metadata, filename_base=None):
    """Downloads the full dataset using a POST request, given the metadata."""
    if not metadata or "variables" not in metadata:
        print(f"    ⚠️ Skipped download for {path}: Missing or invalid metadata.")
        return False

    # Safely encode path for the URL
    encoded_path = quote(path, safe="/")
    url = f"{BASE_URL}/{encoded_path}"

    print(f"    ✅ Attempting download for table: {path}")
    print(f"    ⬇️ POSTing query to: {url}")

    try:
        # Construct query using all values from metadata
        query = {
            "query": [
                {
                    "code": var["code"],
                    "selection": {
                        "filter": "all",
                        "values": ["*"] # Use "all": "*" for PX-Web standard
                    }
                } for var in metadata["variables"]
            ],
            "response": {
                "format": "json-stat2" # Or "json", "csv", etc. json-stat2 is often detailed
            }
        }

        headers = {
            "Content-Type": "application/json"
        }

        # Step 2: POST to the *same* .px URL with the query
        post_response = requests.post(url, headers=headers, json=query, timeout=120) # Longer timeout for download
        time.sleep(SLEEP_TIME) # Wait AFTER the request
        post_response.raise_for_status()
        data = post_response.json()

        # Step 3: Save result
        output_file_base = filename_base or path.replace("/", "_").replace(".px", "")
        output_filepath = os.path.join(OUTPUT_DIR, f"{output_file_base}.json")

        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"    ✅ Saved: {output_filepath}")
        return True

    except requests.exceptions.HTTPError as http_err:
        print(f"    ❌ HTTP Error downloading {path}: {http_err}")
        if http_err.response is not None:
             try:
                 print(f"       📄 Server Response: {http_err.response.text[:500]}...")
             except Exception:
                 print("       📄 Server Response: (Could not decode)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"    ❌ General Error downloading {path}: {e}")
        return False
    except json.JSONDecodeError as e:
         print(f"   ❌ JSON Decode Error processing download response for {path}: {e}")
         print(f"      📄 Raw Response: {post_response.text[:500]}...")
         return False


def build_tree(path=""):
    """Recursively builds the API tree and attempts downloads."""
    items = fetch(path)
    if items is None:
        return {"ERROR": f"Failed to fetch structure at {path}"}

    tree = {}

    # Handle cases where the response might be a dictionary (like root) instead of list
    if isinstance(items, dict) and 'links' in items:
        # Adjust if the root structure is different, e.g., has a 'links' key
         items_to_process = items['links'] # Or iterate items.values() if relevant
         print(f"ℹ️ Processing dictionary structure at '{path or 'root'}' (using 'links')")
    elif isinstance(items, list):
        items_to_process = items
    else:
        print(f"⚠️ Unexpected data type returned from fetch({path}): {type(items)}")
        return {"ERROR": f"Unexpected data type at {path}"}


    for item in items_to_process:
        # Adapt based on actual item structure (might be string or dict)
        item_id = None
        item_type = None
        sub_path = None

        if isinstance(item, str):
            # If API returns just strings for nodes
            item_id = item
            item_type = "d" # Assume directory/folder if just a string name
            print(f"📁 Found string node: {item_id}")

        elif isinstance(item, dict):
            # Common PXWeb structure
            item_id = item.get("id") or item.get("dbid") # Use 'id' first, fallback to 'dbid'
            item_type = item.get("type")
            if item_id is None:
                print(f"⚠️ Skipping item with no id: {item}")
                continue
            print(f"ℹ️ Processing item: {item_id} (type: {item_type})")

        else:
            print(f"⚠️ Skipping unknown item format: {item}")
            continue

        # Construct the path for the next level
        sub_path = f"{path}/{item_id}" if path else item_id
        safe_sub_path = sub_path.replace("\\", "/") # Normalize potential windows paths

        # Default assumption: It's a directory to explore further
        node_content = {"STATUS": "PENDING_EXPLORE"}

        # Check if it looks like a table file (.px suffix)
        is_potential_table = item_id.lower().endswith(".px")

        if item_type == 't' or is_potential_table:
            print(f"  📄 Potential table detected: {safe_sub_path}")
            probe_result = summarize_and_get_metadata(safe_sub_path)

            if probe_result is None:
                 print(f"    ⚠️ Probe failed for {safe_sub_path}. Marking as UNKNOWN.")
                 node_content = {"STATUS": "PROBE_FAILED"}
            elif probe_result["type"] == "TABLE":
                 print(f"    ✅ Probe successful. Attempting download.")
                 node_content = probe_result["summary"] # Store summary
                 # Attempt download using the fetched metadata
                 success = download_dataset(safe_sub_path, probe_result["metadata"])
                 if not success:
                     print(f"    ⚠️ Download failed for: {safe_sub_path}")
                     node_content["STATUS"] = "DOWNLOAD_FAILED" # Add status to summary
                 else:
                     node_content["STATUS"] = "DOWNLOAD_SUCCESS"
            elif probe_result["type"] == "SUBTREE":
                 print(f"    ⚠️ Probe indicated SUBTREE (list) for .px file? Unexpected. Exploring.")
                 node_content = build_tree(safe_sub_path) # Explore anyway
            elif probe_result["type"] == "UNKNOWN_STRUCTURE":
                print(f"    ⚠️ Probe returned unknown structure for {safe_sub_path}")
                node_content = {"STATUS": "UNKNOWN_STRUCTURE"}
            else: # Should not happen if probe_result is not None
                 print(f"    ⚠️ Probe failed for {safe_sub_path} (unexpected result type). Marking as UNKNOWN.")
                 node_content = {"STATUS": "PROBE_FAILED_UNEXPECTED"}

        elif item_type in ["l", "d", "f"]: # Treat 'l', 'd', 'f' as explorable directories
            print(f"  📂 Entering directory: {safe_sub_path}")
            node_content = build_tree(safe_sub_path) # Recursive call

        elif item_type is None and not is_potential_table:
             print(f"  📂 Item type is '{item_type}' but ID '{item_id}' doesn't end with .px. Assuming directory: {safe_sub_path}")
             node_content = build_tree(safe_sub_path) # Recursive call

        else: # Handle other types if needed, or mark as unknown
            print(f"  ⚠️ Unknown or unhandled item type for {item_id}: {item_type}")
            node_content = f"UNHANDLED_TYPE ({item_type})"

        tree[item_id] = node_content

    return tree

def print_tree(tree, indent=0):
    """Prints the constructed tree structure nicely."""
    for key, value in tree.items():
        prefix = "  " * indent + "├── "
        status = ""
        if isinstance(value, dict):
            # Check for our custom status keys
            stat = value.get("STATUS")
            if stat:
                status = f" [{stat}]"
            if "title" in value: # It's a dataset summary
                 print(f"{prefix}{key}: {value['title']}{status}")
            else: # It's a subtree
                 print(f"{prefix}{key}{status}")
                 print_tree(value, indent + 1) # Recurse into sub-dictionaries
        else: # Simple value (like error messages or unhandled types)
            print(f"{prefix}{key}: {value}")


if __name__ == "__main__":
    print(f"\n📊 Building ÅSUB PXWeb API Tree (saving to '{OUTPUT_DIR}')...")
    print(f"🕒 Using sleep interval: {SLEEP_TIME} seconds")
    api_tree = build_tree()

    print("\n\n📚 Final Tree Structure:\n")
    print_tree(api_tree)

    # Save the final tree structure itself
    tree_file_path = os.path.join(OUTPUT_DIR, "asub_api_structure.json")
    try:
        with open(tree_file_path, "w", encoding="utf-8") as f:
            json.dump(api_tree, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Saved final tree structure to: {tree_file_path}")
    except Exception as e:
        print(f"\n❌ Failed to save final tree structure: {e}")

    print("\n🏁 Script finished.")
