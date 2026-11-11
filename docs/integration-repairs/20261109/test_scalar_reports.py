"""Scalar evidence must reach structured KPIs and numeric workbook cells."""
from openpyxl import load_workbook
from backend.tests.test_verified_learning_integration import environment
from backend.tests.test_dataplane_integration import case, uploaded, finish, call
from backend.app.dataplane.chat import route
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
from backend.reports.report_generator import ReportGenerator


def test_f011_scalar_evidence_is_exposed_as_kpi_and_excel_number(case, tmp_path):
    snapshot = finish(case, uploaded(case))
    call(case, 'POST', 'metrics', {'dataset_id': snapshot['dataset_id'], 'snapshot_id': snapshot['id'],
         'definition': {'name': 'amount_total', 'column': 'amount', 'aggregation': 'sum',
                        'description': 'Source amount total'}}, 201)
    env, owner, *_ = case
    with env['api']() as db:
        queued = route(db, owner['user'], owner['workspace'], snapshot['dataset_id'], 1,
                       'sum amount', NaturalLanguageAnalyticsService())
    assert queued['status'] == 'queued'
    evidence = finish(case, {'id': queued['plan']['job_id']})
    with env['api']() as db:
        result = route(db, owner['user'], owner['workspace'], snapshot['dataset_id'], 1,
                       'sum amount', NaturalLanguageAnalyticsService())
    assert result['status'] == 'complete'
    assert result.get('kpis') == {'amount_total': evidence['payload']['rows'][0]['value']}
    assert result['kpis']['amount_total'] == 24
    report = ReportGenerator(tmp_path/'reports').generate('analysis', 'xlsx', data=result)
    workbook = load_workbook(report['file_path'], read_only=True, data_only=True)
    try:
        assert workbook.active['B8'].value == 24
        assert workbook.active['B8'].data_type == 'n'
    finally:
        workbook.close()


def test_f011_excel_preserves_high_precision_strings_and_safe_numbers(tmp_path):
    report = ReportGenerator(tmp_path).generate('analysis', 'xlsx', data={'kpis': {
        'integer': 35, 'negative': -5, 'decimal': '1234567890123456.12345678',
        'large_integer': 12345678901234567, 'formula': '=1+1'}})
    workbook = load_workbook(report['file_path'], read_only=True, data_only=True)
    try:
        values = [workbook.active.cell(row, 2).value for row in range(8, 13)]
        assert values == [35, -5, '1234567890123456.12345678', '12345678901234567', '=1+1']
    finally:
        workbook.close()
