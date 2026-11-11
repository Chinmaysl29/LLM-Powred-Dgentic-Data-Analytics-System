"""CSV reports must preserve persisted evidence and reject unknown formats."""
import csv
import io
from backend.tests.test_integration_repair_reports import report_source
from backend.tests.test_analysis_history_and_reports import settings, db_engine, db_session, client
from backend.reports.report_generator import ReportGenerator


def test_f010_csv_report_download_matches_persisted_analysis(client, db_session, monkeypatch, tmp_path):
    _, _, headers, analysis = report_source(client, db_session, monkeypatch, tmp_path)
    generated = client.post('/api/v1/reports/from-analysis', headers=headers,
                            json={'run_id': analysis['run_id'], 'format_type': 'csv'})
    assert generated.status_code == 201
    downloaded = client.get('/api/v1/reports/'+generated.json()['id']+'/download', headers=headers)
    assert downloaded.status_code == 200
    rows = list(csv.DictReader(io.StringIO(downloaded.content.decode('utf-8-sig'))))
    assert analysis['data']
    assert rows == [{k: '' if v is None else str(v) for k, v in row.items()} for row in analysis['data']]


def test_f010_unknown_report_format_is_validation_error(client, db_session, monkeypatch, tmp_path):
    _, _, headers, analysis = report_source(client, db_session, monkeypatch, tmp_path)
    response = client.post('/api/v1/reports/from-analysis', headers=headers,
                           json={'run_id': analysis['run_id'], 'format_type': 'unsupported'})
    assert response.status_code == 422


def test_f010_csv_quoting_and_formula_strings(tmp_path):
    report = ReportGenerator(tmp_path).generate('analysis', 'csv', data={
        'data': [{'label': '=1+1', 'amount': -5}, {'label': 'comma, quote " and\nnewline', 'amount': 35}]})
    with open(report['file_path'], encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [{'label': "'=1+1", 'amount': '-5'},
                    {'label': 'comma, quote " and\nnewline', 'amount': '35'}]
