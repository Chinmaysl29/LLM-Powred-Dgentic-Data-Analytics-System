"""Build synthetic acceptance inputs only; never connect to application storage.

Run with the backend Python environment. Expected answers use stdlib arithmetic,
not application analytics. All output stays under tests/fixtures/integration.
"""
import csv
import json
from pathlib import Path
from statistics import mean, median, variance

from openpyxl import Workbook
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/integration"


def write_csv(name, rows):
    with (ROOT / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    amounts = [100, 200, -50, 0, 250, 1000]
    rows = [dict(transaction_id=f"T{i+1}", customer_id=f"C{i%3+1}",
                 product_id=f"P{i%3+1}", region=["North", "South"][i%2],
                 order_date=f"2026-0{1+i//3}-0{1+i%3}", revenue=value)
            for i, value in enumerate(amounts)]
    write_csv("retail.csv", rows)
    dirty = rows + [dict(rows[1]), dict(rows[0], transaction_id="T7", revenue=None)]
    write_csv("missing_duplicates.csv", dirty)
    write_csv("customers.csv", [dict(customer_id=f"C{i}", segment=segment)
                                for i, segment in enumerate(["Retail", "SMB", "Enterprise"], 1)])
    products = [dict(product_id=f"P{i}", category=category)
                for i, category in enumerate(["Hardware", "Software", "Services"], 1)]
    (ROOT / "products.json").write_text(json.dumps(products, indent=2) + "\n")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Synthetic retail"
    sheet.append(list(rows[0]))
    for row in rows:
        sheet.append(list(row.values()))
    workbook.save(ROOT / "retail.xlsx")
    monthly = [dict(month=f"{2023+i//12}-{i%12+1:02d}-01",
                    revenue=1000+20*i+(300 if i%12 in (10, 11) else 0)) for i in range(36)]
    write_csv("monthly_revenue.csv", monthly)
    expected = {
        "label": "SYNTHETIC ACCEPTANCE FIXTURES - NOT CUSTOMER DATA",
        "retail": {"rows": 6, "sum": 1500, "mean": 250, "median": 150,
                   "min": -50, "max": 1000, "sample_variance": variance(amounts),
                   "region_totals": {"North": 300, "South": 1200},
                   "monthly_totals": {"2026-01": 250, "2026-02": 1250},
                   "product_totals": {"P1": 100, "P2": 450, "P3": 950}},
        "missing_duplicates": {"rows": 8, "exact_duplicate_rows": 1,
                               "missing_revenue": 1, "sum_non_null": 1700,
                               "mean_non_null": mean(amounts+[200]),
                               "median_non_null": median(amounts+[200])},
        "relationships": {"unmatched_customers": 0, "unmatched_products": 0},
        "monthly_revenue": {"rows": 36, "sum": 50400,
                            "first": 1000, "last": 2000},
        "semantics": {"revenue": "Signed amount in USD; refunds are negative.",
                      "duplicate_policy": "Preserve rows until explicit deduplication approval.",
                      "missing_policy": "Exclude missing revenue from mean; never replace it with zero.",
                      "outlier_policy": "Retain large values until investigation; no automatic deletion."},
    }
    assert sum(amounts) == expected["retail"]["sum"]
    assert sum(row["revenue"] for row in monthly) == expected["monthly_revenue"]["sum"]
    (ROOT / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    styles = getSampleStyleSheet()
    story = [Paragraph("Synthetic business definitions", styles["Title"]),
             Paragraph(expected["label"], styles["Heading2"]), Spacer(1, 20)]
    for term, definition in expected["semantics"].items():
        story.extend([Paragraph(term.replace("_", " ").title(), styles["Heading2"]),
                      Paragraph(definition, styles["BodyText"]), Spacer(1, 12)])
    story.append(Paragraph("This reference describes test fixtures only. It provides no factual claims about a customer business.", styles["BodyText"]))
    SimpleDocTemplate(str(ROOT / "business_definitions.pdf")).build(story)
    print(f"Created synthetic fixtures in {ROOT}")


if __name__ == "__main__":
    main()
