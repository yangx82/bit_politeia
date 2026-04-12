import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Create a minimal valid PDF
with open("test.pdf", "wb") as f:
    f.write(
        b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Resources <<\n/Font << /F1 4 0 R >>\n>>\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 24 Tf\n100 700 Td\n(Hello World) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n0000000224 00000 n \n0000000301 00000 n \ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n396\n%%EOF"
    )

print("Created valid test.pdf at", os.path.abspath("test.pdf"))

# Load skills
skill_manager.load_skills()

# Find the tool
tools = skill_manager.get_skill_tools()
pdf_tool = next((t for t in tools if "pdf-reader" in t.name), None)

if pdf_tool:
    print(f"Found tool: {pdf_tool.name}")
    abs_path = os.path.abspath("test.pdf")
    # Execute
    result = pdf_tool.run(abs_path)
    print("Execution Result:", result)
else:
    print("PDF tool not found!")
