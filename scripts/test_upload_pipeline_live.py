"""Test end-to-end dataset upload pipeline against running backend."""

import io
import json
from pathlib import Path
import httpx
import pandas as pd

BASE_URL = "http://localhost:8000/api/v1"

def test_pipeline():
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Health check & Authentication
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[PASS] 1. Health check passed")

    email = "live_test_user@example.com"
    password = "TestPassword123!"
    res = client.post("/auth/login", json={"email": email, "password": password})
    if res.status_code != 200:
        res = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Live Test User"})
        res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Auth failed: {res.text}"
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("[PASS] 1b. Authenticated with JWT access token")

    # 2. Upload CSV
    csv_content = b"id,customer,revenue\n1,Alice,1200\n2,Bob,2400\n3,Charlie,3100\n"
    res = client.post(
        "/datasets/upload",
        files={"file": ("customers.csv", csv_content, "text/csv")},
        data={"dataset_name": "Customers CSV Test"},
    )
    assert res.status_code == 201, f"CSV upload failed: {res.status_code} {res.text}"
    csv_data = res.json()
    csv_id = csv_data["dataset_id"]
    print(f"[PASS] 2. CSV upload passed: id={csv_id}")

    # 3. Upload Excel (.xlsx)
    excel_buf = io.BytesIO()
    df_excel = pd.DataFrame({
        "order_id": [101, 102, 103],
        "product": ["Widget A", "Widget B", "Widget C"],
        "price": [19.99, 45.50, 99.00]
    })
    df_excel.to_excel(excel_buf, index=False)
    excel_buf.seek(0)
    res = client.post(
        "/datasets/upload",
        files={"file": ("orders.xlsx", excel_buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dataset_name": "Orders Excel Test"},
    )
    assert res.status_code == 201, f"Excel upload failed: {res.status_code} {res.text}"
    excel_data = res.json()
    excel_id = excel_data["dataset_id"]
    print(f"[PASS] 3. Excel upload passed: id={excel_id}")

    # 4. Upload JSON
    json_records = [
        {"sku": "SKU-001", "name": "Keyboard", "stock": 45},
        {"sku": "SKU-002", "name": "Mouse", "stock": 120},
        {"sku": "SKU-003", "name": "Monitor", "stock": 15}
    ]
    res = client.post(
        "/datasets/upload",
        files={"file": ("inventory.json", json.dumps(json_records).encode("utf-8"), "application/json")},
        data={"dataset_name": "Inventory JSON Test"},
    )
    assert res.status_code == 201, f"JSON upload failed: {res.status_code} {res.text}"
    json_data = res.json()
    json_id = json_data["dataset_id"]
    print(f"[PASS] 4. JSON upload passed: id={json_id}")

    # 5. Upload PDF
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Annual Financial Report\nQ4 Summary: Revenue grew 25% year over year.\nNet Profit: $4.5M.")
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post(
        "/datasets/upload",
        files={"file": ("annual_report.pdf", pdf_bytes, "application/pdf")},
        data={"dataset_name": "Annual Report PDF Test"},
    )
    assert res.status_code == 201, f"PDF upload failed: {res.status_code} {res.text}"
    pdf_data = res.json()
    pdf_id = pdf_data["dataset_id"]
    print(f"[PASS] 5. PDF upload passed: id={pdf_id}")

    # 6. Verify filesystem storage structure
    storage_root = Path("/app/storage") if Path("/app/storage").exists() else Path("storage")
    assert storage_root.exists(), "storage/ directory does not exist!"
    assert (storage_root / "raw").exists(), "storage/raw/ does not exist!"
    assert (storage_root / "processed").exists(), "storage/processed/ does not exist!"
    assert (storage_root / "datasets").exists(), "storage/datasets/ does not exist!"
    assert (storage_root / "vectorized").exists(), "storage/vectorized/ does not exist!"

    print("[PASS] 6. Base storage directories verified: raw, processed, datasets, vectorized")

    # Verify per-dataset registry artifacts for tabular datasets
    for did in [csv_id, excel_id, json_id]:
        ds_dir = storage_root / "datasets" / did
        assert ds_dir.exists(), f"Dataset directory missing for {did}"
        assert (ds_dir / "metadata.json").exists(), f"metadata.json missing in {ds_dir}"
        assert (ds_dir / "profile.json").exists(), f"profile.json missing in {ds_dir}"
        assert (ds_dir / "quality.json").exists(), f"quality.json missing in {ds_dir}"
        assert (ds_dir / "versions.json").exists(), f"versions.json missing in {ds_dir}"
        assert (ds_dir / "lineage.json").exists(), f"lineage.json missing in {ds_dir}"
        print(f"[PASS] Dataset registry verified for {did}: metadata, profile, quality, versions, lineage exist")

    # Verify processed canonical JSON
    csv_processed = storage_root / "processed" / f"{csv_id}.json"
    assert csv_processed.exists(), f"Processed canonical JSON missing: {csv_processed}"
    csv_records = json.loads(csv_processed.read_text(encoding="utf-8"))
    assert isinstance(csv_records, list), "CSV processed JSON must be a list of records"
    assert len(csv_records) == 3
    assert csv_records[0]["customer"] == "Alice"
    print(f"[PASS] CSV canonical JSON conversion verified: {len(csv_records)} records")

    # Verify PDF raw file storage
    pdf_raw = Path(pdf_data["file_path"])
    assert pdf_raw.exists(), f"Raw PDF file missing: {pdf_raw}"
    print(f"[PASS] PDF stored source verified: {pdf_raw.stat().st_size} bytes")

    # 7. Verify API retrieval and downstream availability
    res = client.get(f"/datasets/{csv_id}")
    assert res.status_code == 200
    res = client.get(f"/datasets/{csv_id}/metadata")
    assert res.status_code == 200
    res = client.get(f"/datasets/{csv_id}/profile")
    assert res.status_code == 200
    res = client.get(f"/datasets/{csv_id}/quality")
    assert res.status_code == 200
    res = client.get(f"/datasets/{csv_id}/versions")
    assert res.status_code == 200
    print("[PASS] 7. API retrieval endpoints verified (GET dataset, metadata, profile, quality, versions)")

    print("\n==========================================")
    print("ALL ENTERPRISE PIPELINE CHECKS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    test_pipeline()
