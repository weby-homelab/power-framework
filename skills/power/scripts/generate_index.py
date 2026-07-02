#!/usr/bin/env python3
import os
import re
from datetime import datetime

VAULT_DIR = "/root/geminicli/brain"
INDEX_PATH = os.path.join(VAULT_DIR, "index.md")
LOG_PATH = os.path.join(VAULT_DIR, "log.md")

def parse_metadata(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Simple YAML parsing
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", content, re.DOTALL)
    if not match:
        return None
        
    yaml_content = match.group(1)
    meta = {}
    for line in yaml_content.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip('"').strip("'")
            
    return meta

def main():
    concepts = {}
    
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", "05_Templates", "scratch", ".system_generated"]]
        
        for file in files:
            if file.endswith(".md") and file not in ["index.md", "log.md"]:
                filepath = os.path.join(root, file)
                try:
                    meta = parse_metadata(filepath)
                    if meta:
                        m_type = meta.get("type", "Resource")
                        rel_path = os.path.relpath(filepath, VAULT_DIR)
                        title = meta.get("title", file)
                        desc = meta.get("description", "")
                        
                        if m_type not in concepts:
                            concepts[m_type] = []
                        concepts[m_type].append((rel_path, title, desc))
                except Exception as e:
                    print(f"Error parsing metadata for {filepath}: {e}")
                    
    # Generate index.md content
    index_content = []
    index_content.append("---")
    index_content.append("type: System Guide")
    index_content.append('title: "Second Brain Index"')
    index_content.append('description: "Registry of all concepts in the Weby Homelab Second Brain"')
    index_content.append(f"timestamp: {datetime.now().isoformat()}")
    index_content.append("---")
    index_content.append("\n# 🗂️ Weby Homelab Knowledge Catalog (OKF Index)\n")
    index_content.append("Цей файл автоматично підтримується в актуальному стані ШІ-агентами та містить перелік усіх сторінок бази знань, класифікованих за типами.\n")
    
    # Sort types alphabetically, or by a defined order
    defined_order = ["System Guide", "Project", "Area", "Resource", "Daily Log", "Archive"]
    sorted_types = sorted(concepts.keys(), key=lambda t: defined_order.index(t) if t in defined_order else 99)
    
    for m_type in sorted_types:
        index_content.append(f"## 📁 {m_type}s")
        items = sorted(concepts[m_type], key=lambda x: x[1]) # sort by title
        for rel_path, title, desc in items:
            # Format as clickable markdown file link
            index_content.append(f"- **[{title}]({rel_path})** — {desc}")
        index_content.append("")
        
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(index_content))
        
    print(f"Generated index.md with {sum(len(v) for v in concepts.values())} concepts.")

    # Generate log.md if it doesn't exist
    if not os.path.exists(LOG_PATH):
        log_content = []
        log_content.append("---")
        log_content.append("type: System Guide")
        log_content.append('title: "Second Brain Change Log"')
        log_content.append('description: "Append-only chronological log of operations"')
        log_content.append(f"timestamp: {datetime.now().isoformat()}")
        log_content.append("---")
        log_content.append("\n# 📝 Chronological Second Brain Change Log\n")
        log_content.append(f"## [{datetime.now().strftime('%Y-%m-%d')}] initialization")
        log_content.append("- **Action:** Initialized OKF / LLM-Wiki schema overlay across the vault.")
        log_content.append(f"- **Result:** Migrated {sum(len(v) for v in concepts.values())} files to OKF format and compiled index.")
        
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(log_content))
        print("Generated initial log.md")

if __name__ == "__main__":
    main()
