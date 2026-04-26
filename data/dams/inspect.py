import xlrd, os

dam_dir = os.path.dirname(__file__)
files = sorted([f for f in os.listdir(dam_dir) if f.endswith('.xls')])
print(f"Files: {files}\n")

for fname in files[:2]:
    path = os.path.join(dam_dir, fname)
    wb = xlrd.open_workbook(path)
    print(f"=== {fname} ===")
    print(f"  Sheets: {wb.sheet_names()}")
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        print(f"  Sheet '{sheet_name}': {sh.nrows} rows x {sh.ncols} cols")
        for r in range(min(20, sh.nrows)):
            row = [sh.cell_value(r, c) for c in range(sh.ncols)]
            print(f"    Row {r}: {row}")
    print()
