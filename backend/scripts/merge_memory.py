import json
import sys
import os

def merge_jsonl(file1, file2, output_file):
    print(f"Merging {file1} and {file2} into {output_file}...")
    
    entries = []
    metadata = None
    
    # Read first file
    try:
        with open(file1, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        if not metadata: metadata = data
                        continue
                    entries.append(data)
                except json.JSONDecodeError:
                    continue
        print(f"Loaded {len(entries)} messages from {file1}")
    except Exception as e:
        print(f"Error reading {file1}: {e}")
        return

    # Read second file
    count2 = 0
    try:
        with open(file2, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        if not metadata: metadata = data
                        continue
                    entries.append(data)
                    count2 += 1
                except json.JSONDecodeError:
                    continue
        print(f"Loaded {count2} messages from {file2}")
    except Exception as e:
        print(f"Error reading {file2}: {e}")
        return

    # Deduplicate by ID
    unique_entries = {}
    for entry in entries:
        uid = entry.get('id')
        if not uid:
            uid = str(hash(json.dumps(entry, sort_keys=True)))
        unique_entries[uid] = entry
        
    final_list = list(unique_entries.values())

    # Sort by timestamp
    final_list.sort(key=lambda x: x.get("timestamp", ""))

    print(f"Total unique messages after deduplication: {len(final_list)}")

    # Write output
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            if metadata:
                f.write(json.dumps(metadata) + "\n")
            for entry in final_list:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Successfully wrote merged file to: {output_file}")
        print("\n[ACTION REQUIRED]: Backup your current chat.jsonl, then rename this merged file to chat.jsonl and restart the backend.")
    except Exception as e:
        print(f"Error writing to {output_file}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python merge_memory.py <path_to_old_chat.jsonl> <path_to_new_chat.jsonl> <output_chat.jsonl>")
        sys.exit(1)
        
    merge_jsonl(sys.argv[1], sys.argv[2], sys.argv[3])
