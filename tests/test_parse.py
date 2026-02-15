
import os
import re

def _parse_requests(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        content = f.read()
    
    requests_list = []
    sections = content.split("---")
    for section in sections:
        # Improved regex to capture the whole title after the ID
        id_match = re.search(r"## (REQ-\d+): (.*)", section)
        if id_match:
            req_id = id_match.group(1)
            full_title = id_match.group(2).strip()
            
            # Metadata extraction
            def get_meta(pattern, default="UNKNOWN"):
                m = re.search(pattern, section)
                return m.group(1).strip() if m else default

            author = get_meta(r"\*\*From:\*\* (.*)")
            date = get_meta(r"\*\*Date:\*\* (.*)")
            req_type_meta = get_meta(r"\*\*Type:\*\* (.*)")
            
            # Type detection logic
            req_type = "UNKNOWN"
            if req_type_meta != "UNKNOWN":
                req_type = req_type_meta
            else:
                clean_title = full_title.split(" — ")[0]
                if "Request" in clean_title:
                    req_type = clean_title.replace("Request", "").strip()
                elif "Report" in clean_title:
                    req_type = clean_title.replace("Report", "").strip()
                elif "Plan" in clean_title:
                    req_type = clean_title.replace("Plan", "").strip()
            
            # Status detection logic
            status = "UNKNOWN"
            if "### Status" in section:
                status_part = section.split("### Status")[1].strip()
                # Look for **STATUS**
                status_match = re.search(r"\*\*(.*?)\*\*", status_part)
                if status_match:
                    status = status_match.group(1)

            # Summary extraction
            summary = ""
            if "### Description" in section:
                summary = section.split("### Description")[1].split("###")[0].strip()
            
            if not summary:
                # Fallback: try to find any text that is not metadata or headers
                lines = section.split("\n")
                summary_lines = []
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if line.startswith("#"): continue
                    if line.startswith("**"): continue
                    summary_lines.append(line)
                summary = " ".join(summary_lines).strip()

            requests_list.append({
                "id": req_id,
                "title": full_title,
                "type": req_type.upper(),
                "status": status.upper(),
                "author": author,
                "date": date,
                "summary": summary[:100] + ("..." if len(summary) > 100 else "")
            })
    return requests_list

requests = _parse_requests("_cortex/requests.md")
for r in requests:
    print(f"{r['id']} | {r['type']} | {r['status']} | {r['author']}")
    print(f"  Summary: {r['summary']}")
