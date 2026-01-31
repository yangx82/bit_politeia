import zipfile
import xml.etree.ElementTree as ET
import os

def convert_docx_to_md(docx_path, md_path):
    # Namespace map
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    
    try:
        with zipfile.ZipFile(docx_path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            
            lines = []
            
            # Find body
            body = tree.find('w:body', ns)
            if body is None:
                print("No body found")
                return

            for p in body.findall('w:p', ns):
                paragraph_text = []
                # Check for styles/headings (simplified)
                pPr = p.find('w:pPr', ns)
                style = ""
                if pPr is not None:
                    pStyle = pPr.find('w:pStyle', ns)
                    if pStyle is not None:
                        val = pStyle.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')
                        # Map some styles if needed, though simple text extraction is usually enough
                        
                for r in p.findall('w:r', ns):
                    t = r.find('w:t', ns)
                    if t is not None:
                         if t.text:
                            paragraph_text.append(t.text)
                
                if paragraph_text:
                    lines.append("".join(paragraph_text))
            
            # Write key paragraphs to MD
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write("# Architecture Document Content\n\n")
                for line in lines:
                    f.write(line + "\n\n")
                    
            print(f"Successfully converted {docx_path} to {md_path}")
            
    except Exception as e:
        print(f"Error converting file: {e}")

if __name__ == "__main__":
    docx = "d:/BaiduSyncdisk/SIAT/coding/bit_politeia/Bit_Politeia_architecture_frontend.docx"
    md = "d:/BaiduSyncdisk/SIAT/coding/bit_politeia/docs/Bit_Politeia_architecture_frontend.md"
    convert_docx_to_md(docx, md)
