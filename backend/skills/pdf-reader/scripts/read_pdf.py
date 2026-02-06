import sys
import json
import argparse
from pypdf import PdfReader

def read_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return {"success": True, "text": text, "pages": len(reader.pages)}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Handle arguments. 
    # SkillManager calls: python script.py "argument_string"
    # We expect the argument to be the file path directly or a JSON string.
    
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No file path provided"}))
        sys.exit(1)
        
    input_arg = sys.argv[1]
    
    # Simple check if it's a file path
    file_path = input_arg.strip()
    
    # If the input is a JSON string (e.g. from structured tool call), parse it
    # But for this simple skill, we'll assume the input IS the file path if it doesn't look like JSON
    if input_arg.startswith("{"):
         try:
             data = json.loads(input_arg)
             file_path = data.get("file_path", file_path)
         except:
             pass

    result = read_pdf(file_path)
    print(json.dumps(result))
