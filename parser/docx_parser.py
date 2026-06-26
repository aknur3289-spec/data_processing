from docx import Document
import argparse
import json
import os
import re
import tempfile
import zipfile


def clean_price(val):
    if val is None:
        return 0.0

    s = str(val).strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\d.,]", "", s)
    s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return 0.0


def clean_string(val):
    if val is None:
        return ""

    s = str(val).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_docx(file_path):
    try:
        doc = Document(file_path)
        print(f"✅ DOCX opened: {file_path}")
    except Exception as e:
        print(f"❌ DOCX error: {file_path} | {e}")
        return []

    results = []

    for table in doc.tables:
        header_row = None
        header_index = None

        for row_index, row in enumerate(table.rows):
            cells = [cell.text.strip() for cell in row.cells]
            lower_cells = [c.lower() for c in cells]

            has_code = any("код" in c for c in lower_cells)
            has_name = any("наименование" in c for c in lower_cells)
            has_price = any(
                "стоимость" in c or "цена" in c or "тенге" in c or "сумма" in c
                for c in lower_cells
            )

            if has_name and (has_price or has_code):
                header_row = cells
                header_index = row_index
                break

        if header_row is None:
            continue

        code_idx = None
        name_idx = None
        price_idx = None

        for i, cell in enumerate(header_row):
            lower = cell.lower()

            if "код" in lower and "наименование" not in lower:
                code_idx = i

            if "наименование" in lower or "услуга" in lower:
                name_idx = i

            if (
                "стоимость" in lower
                or "цена" in lower
                or "тенге" in lower
                or "сумма" in lower
            ):
                price_idx = i

        if name_idx is None or price_idx is None:
            continue

        for row in table.rows[header_index + 1:]:
            cells = [cell.text.strip() for cell in row.cells]

            if len(cells) <= max(name_idx, price_idx):
                continue

            name = clean_string(cells[name_idx]) if name_idx < len(cells) else ""
            if not name:
                continue

            name_lower = name.lower()
            if name_lower.startswith(("раздел", "блок", "итого", "всего")):
                continue

            price = clean_price(cells[price_idx]) if price_idx < len(cells) else 0.0
            if price == 0.0:
                continue

            code = (
                clean_string(cells[code_idx])
                if code_idx is not None and code_idx < len(cells)
                else None
            )

            results.append({
                "source_file": os.path.basename(file_path),
                "service_code_source": code,
                "service_name_raw": name,
                "price_resident_kzt": price,
                "price_sng_kzt": price,
                "price_nonresident_kzt": price
            })

    return results


def parse_zip(zip_path):
    all_results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)

        for root, _, files in os.walk(tmpdir):
            for file in files:
                if file.lower().endswith(".docx") and not file.startswith("~$"):
                    full_path = os.path.join(root, file)
                    print(f"\n📄 Parsing DOCX: {file}")
                    all_results.extend(parse_docx(full_path))

    return all_results


def parse_input(path):
    if path.lower().endswith(".zip"):
        return parse_zip(path)

    if path.lower().endswith(".docx"):
        return parse_docx(path)

    raise ValueError("Only .docx or .zip files are supported")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to .docx file or .zip archive")
    parser.add_argument("--out", default=None, help="Output JSON file")
    args = parser.parse_args()

    results = parse_input(args.input)

    print(f"\n📊 Total services found: {len(results)}")

    if results:
        print("\n📋 First 5 rows:")
        for idx, item in enumerate(results[:5], 1):
            print(f"{idx}. {item['service_name_raw'][:60]}")
            print(f"   Code: {item['service_code_source']}")
            print(f"   Price: {item['price_resident_kzt']}")
            print(f"   Source: {item['source_file']}")
            print()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"✅ Saved to {args.out}")


if __name__ == "__main__":
    main()