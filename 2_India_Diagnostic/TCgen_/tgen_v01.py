import pandas as pd
import tkinter as tk
from tkinter import filedialog
import os

# ================================
# Excel file selection (menu)
# ================================
root = tk.Tk()
root.withdraw()  # Hide main window

excel_path = filedialog.askopenfilename(
    title="Select Diagnostic Database Excel File",
    filetypes=[("Excel files", "*.xlsx *.xls")]
)

if not excel_path:
    print("❌ No Excel file selected. Program terminated.")
    exit(1)

# ================================
# Output file path (same folder as Excel)
# ================================
base_dir = os.path.dirname(excel_path)
txt_path = os.path.join(base_dir, "testcase___.txt")

# ================================
# Read the Excel file
# ================================
df = pd.read_excel(excel_path)

# ================================
# Filter rows where column I contains "checkbox is enabled"
# (original logic preserved)
# ================================
filtered_df = df[df.iloc[:, 15].astype(str).str.upper() == "TRUE"]

# ================================
# Select and reorder specific columns
# (original logic preserved)
# ================================
df_subset = filtered_df.iloc[:, [0, 6, 3, 5, 7, 12, 13, 14, 9, 10, 11]]

# ================================
# Format each row
# ================================
def format_row(row):
    row = row.astype(str).tolist()
    return f"{row[0]} , {','.join(row[1:])}"

# Header
header = df_subset.columns.astype(str).tolist()
header_line = f"{header[0]} , {', '.join(header[1:])}"

# Data rows
data_lines = df_subset.apply(format_row, axis=1).tolist()

# Combine header + data
all_lines = [header_line] + data_lines

# ================================
# Write to text file
# ================================
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write('#')
    for line in all_lines:
        f.write(line + '\n')

print("✅ Excel file selected :", excel_path)
print("✅ Testcase file saved :", txt_path)
