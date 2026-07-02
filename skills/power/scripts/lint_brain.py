#!/usr/bin/env python3
import os
import re
from pathlib import Path

VAULT_DIR = Path("/root/geminicli/brain").resolve()
EXCLUDE_DIRS = [".git", "05_Templates", "scratch", ".system_generated"]
EXCLUDE_ORPHAN_FILES = [
    "README.md", "Home.md", "index.md", "log.md", 
    "Successor-Hub.md", "PARA-OKF-LLM_Wiki.md", "Weby_PARA-OKF-LLM_Wiki.md"
]

def clean_note_name(name):
    # Remove file extension and strip
    return name.replace(".md", "").strip().lower()

def main():
    all_files = {}  # clean_name -> absolute_path
    rel_paths = {}  # clean_name -> relative_path
    links = {}      # relative_path -> list of target clean names
    untyped_files = []
    broken_links = []
    
    # 1. First pass: Collect all note names
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".md"):
                abs_path = Path(root) / file
                rel_path = os.path.relpath(abs_path, VAULT_DIR)
                clean_name = clean_note_name(file)
                all_files[clean_name] = abs_path
                rel_paths[clean_name] = rel_path
                
    # 2. Second pass: Parse files for frontmatter and links
    for clean_name, abs_path in all_files.items():
        rel_path = rel_paths[clean_name]
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Check OKF frontmatter
        has_frontmatter = content.startswith("---")
        if not has_frontmatter:
            untyped_files.append((rel_path, "No YAML frontmatter block"))
        else:
            # Parse type
            match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", content, re.DOTALL)
            if match:
                yaml_content = match.group(1)
                if "type:" not in yaml_content:
                    untyped_files.append((rel_path, "Missing required 'type' field"))
            else:
                untyped_files.append((rel_path, "Malformed YAML frontmatter"))
                
        # Find all Obsidian wiki-links: [[Link]] or [[Link|Alias]]
        wiki_links = re.findall(r"\[\[(.*?)\]\]", content)
        file_links = []
        for link in wiki_links:
            # Strip alias and header anchor if present
            target = link.split("|")[0].split("#")[0].strip()
            if target:
                file_links.append(clean_note_name(target))
                
        # Find all GFM markdown links: [Text](Path.md)
        gfm_links = re.findall(r"\[.*?\]\((.*?\.md)(?:#.*?)?\)", content)
        for link in gfm_links:
            # Get the base filename without extension
            target = os.path.basename(link)
            if target:
                file_links.append(clean_note_name(target))
                
        links[rel_path] = file_links
        
    # 3. Check for broken links
    for rel_path, targets in links.items():
        for target in targets:
            # Check if target is a valid note name
            if target not in all_files:
                # Also check if it matches a sub-folder name or relative file link
                direct_file = VAULT_DIR / f"{target}.md"
                if not direct_file.exists():
                    broken_links.append((rel_path, target))
                    
    # 4. Check for orphan files (files that have no inbound links)
    inbound_counts = {rel_path: 0 for rel_path in links.keys()}
    for rel_path, targets in links.items():
        for target in targets:
            if target in all_files:
                target_rel_path = rel_paths[target]
                inbound_counts[target_rel_path] += 1
                
    orphans = []
    for rel_path, count in inbound_counts.items():
        filename = os.path.basename(rel_path)
        if count == 0 and filename not in EXCLUDE_ORPHAN_FILES and not rel_path.startswith("06_Daily_Logs/"):
            orphans.append(rel_path)
            
    # 5. Print health report
    print("=== 🧹 Second Brain Health Lint Report ===")
    print(f"Total markdown notes scanned: {len(all_files)}\n")
    
    has_issues = False
    
    if untyped_files:
        has_issues = True
        print(f"⚠️  Missing/Invalid OKF Metadata ({len(untyped_files)}):")
        for rel_path, reason in sorted(untyped_files):
            print(f"  - {rel_path}: {reason}")
        print()
        
    if broken_links:
        has_issues = True
        print(f"❌ Broken links found ({len(broken_links)}):")
        for rel_path, target in sorted(broken_links):
            print(f"  - In {rel_path}: link to [[{target}]] cannot be resolved")
        print()
        
    if orphans:
        has_issues = True
        print(f"🕷️  Orphan notes (no inbound links) ({len(orphans)}):")
        for rel_path in sorted(orphans):
            print(f"  - {rel_path}")
        print()
        
    if not has_issues:
        print("✅ Vault is completely healthy! Zero errors found.")
        
if __name__ == "__main__":
    main()
