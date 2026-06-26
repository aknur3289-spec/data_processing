import argparse
import json
import os
import re
import tempfile
import zipfile
from typing import Dict, List, Optional, Union

import pandas as pd


def clean_price(val: Union[str, float, int, None]) -> float:
    if pd.isna(val):
        return 0.0

    s = str(val).strip()
    if not s:
        return 0.0

    s = re.sub(r"\s+", "", s)

    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            if re.search(r",(\d{3})$", s):
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")

    s = re.sub(r"[^\d.]", "", s)

    if not s:
        return 0.0

    if s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(s)
    except ValueError:
        return 0.0


def clean_string(val: Union[str, float, int, None]) -> str:
    if pd.isna(val):
        return ""

    s = str(val).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_cell_val(val: Union[str, float, int, None]) -> str:
    if pd.isna(val):
        return ""

    if isinstance(val, float) and val.is_integer():
        val = int(val)

    s = str(val).strip()

    if s.endswith(".0"):
        s = s[:-2]

    return s


def parse_sheet(df: pd.DataFrame, source_file: str, sheet_name: str) -> List[Dict[str, Union[str, float, None]]]:
    strategy = None
    header_row_idx = None

    code_col = None
    name_col = None
    res_col = None
    sng_col = None
    nonres_col = None

    num_rows = df.shape[0]

    for i in range(num_rows):
        row_vals = df.iloc[i].tolist()
        normalized_row = [normalize_cell_val(x) for x in row_vals]
        normalized_set = set(normalized_row)

        if {"1", "2", "3", "4", "5", "6", "7", "8"}.issubset(normalized_set):
            strategy = 1
            header_row_idx = i

            for idx, val in enumerate(normalized_row):
                if val == "2":
                    code_col = idx
                elif val == "3":
                    name_col = idx
                elif val == "6":
                    res_col = idx
                elif val == "7":
                    sng_col = idx
                elif val == "8":
                    nonres_col = idx

            break

    if strategy is None:
        for i in range(num_rows):
            row_vals = df.iloc[i].tolist()
            row_clean = [str(x).lower() if not pd.isna(x) else "" for x in row_vals]

            has_name = any("наименование" in x or "услуга" in x for x in row_clean)
            has_price = any("цена" in x or "стоимость" in x for x in row_clean)

            if has_name and has_price:
                strategy = 2
                header_row_idx = i

                for idx, val_str in enumerate(row_clean):
                    if "снг" in val_str or "ближнего зарубежья" in val_str:
                        sng_col = idx
                    elif "дальнего зарубежья" in val_str or "нерезидент" in val_str:
                        nonres_col = idx
                    elif "код" in val_str and "тарификатор" in val_str:
                        code_col = idx
                    elif "код" in val_str:
                        code_col = idx
                    elif "для граждан республики казахстан" in val_str or "резидент" in val_str or "цена" in val_str:
                        res_col = idx
                    elif "наименование" in val_str or "услуга" in val_str:
                        name_col = idx

                break

    if strategy is None:
        return []

    if name_col is None or res_col is None:
        return []

    results = []
    start_row = header_row_idx + 1

    for i in range(start_row, num_rows):
        row = df.iloc[i].tolist()

        if name_col >= len(row):
            continue

        cleaned_name = clean_string(row[name_col])

        if not cleaned_name or cleaned_name.lower() in ("nan", "none"):
            continue

        name_lower = cleaned_name.lower()

        if name_lower.startswith(("раздел", "блок", "итого", "всего")):
            continue

        price_resident = clean_price(row[res_col]) if res_col < len(row) else 0.0
        price_sng = clean_price(row[sng_col]) if sng_col is not None and sng_col < len(row) else price_resident
        price_nonresident = clean_price(row[nonres_col]) if nonres_col is not None and nonres_col < len(row) else price_resident

        if price_resident == 0.0 and price_sng == 0.0 and price_nonresident == 0.0:
            continue

        service_code = None

        if code_col is not None and code_col < len(row):
            cleaned_code = clean_string(row[code_col])
            if cleaned_code and cleaned_code.lower() not in ("nan", "none"):
                service_code = cleaned_code

        results.append({
            "source_file": source_file,
            "source_sheet": sheet_name,
            "service_code_source": service_code,
            "service_name_raw": cleaned_name,
            "price_resident_kzt": price_resident,
            "price_sng_kzt": price_sng,
            "price_nonresident_kzt": price_nonresident
        })

    return results


def parse_xlsx(file_path: str) -> List[Dict[str, Union[str, float, None]]]:
    try:
        sheets = pd.read_excel(file_path, header=None, sheet_name=None, engine="openpyxl")
        print(f"✅ XLSX opened: {file_path}")
    except Exception as e:
        print(f"❌ XLSX error: {file_path} | {e}")
        return []

    all_results = []
    source_file = os.path.basename(file_path)

    for sheet_name, df in sheets.items():
        parsed = parse_sheet(df, source_file, str(sheet_name))

        if parsed:
            print(f"   ✅ Sheet '{sheet_name}': {len(parsed)} rows")
            all_results.extend(parsed)

    return all_results


def parse_zip(zip_path: str) -> List[Dict[str, Union[str, float, None]]]:
    all_results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)

        for root, _, files in os.walk(tmpdir):
            for file in files:
                lower = file.lower()

                if file.startswith("~$"):
                    continue

                if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
                    full_path = os.path.join(root, file)
                    print(f"\n📄 Parsing XLSX: {file}")
                    all_results.extend(parse_xlsx(full_path))

    return all_results


def parse_input(path: str) -> List[Dict[str, Union[str, float, None]]]:
    lower = path.lower()

    if lower.endswith(".zip"):
        return parse_zip(path)

    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        return parse_xlsx(path)

    raise ValueError("Only .xlsx, .xlsm or .zip files are supported")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to .xlsx/.xlsm file or .zip archive")
    parser.add_argument("--out", default=None, help="Output JSON file")
    args = parser.parse_args()

    results = parse_input(args.input)

    print(f"\n📊 Total services found: {len(results)}")

    if results:
        print("\n📋 First 5 rows:")
        for idx, item in enumerate(results[:5], 1):
            print(f"{idx}. {item['service_name_raw'][:60]}")
            print(f"   Code: {item['service_code_source']}")
            print(
                f"   Resident: {item['price_resident_kzt']} | "
                f"SNG: {item['price_sng_kzt']} | "
                f"Nonresident: {item['price_nonresident_kzt']}"
            )
            print(f"   Source: {item['source_file']} | Sheet: {item['source_sheet']}")
            print()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"✅ Saved to {args.out}")


if __name__ == "__main__":
    main()