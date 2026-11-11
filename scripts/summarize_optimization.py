"""Export non-secret metrics and assert complete benchmark response equivalence."""
import json
from pathlib import Path
import statistics


def summarize(root):
    before = json.loads((root/'optimization-before.json').read_text())
    after = json.loads((root/'optimization-final.json').read_text())
    result = {'scope': after['scope'], 'workload': after['workload'], 'platform': after['platform'],
        'versions': after['versions'], 'before_source_hashes': before['source_hashes'],
        'after_source_hashes': after['source_hashes'], 'endpoints': {}}
    for name, baseline in before['endpoints'].items():
        final = after['endpoints'][name]
        assert baseline['response'] == final['response'], name+' response changed'
        measurements = {}
        for label, source in [('before', baseline), ('after', final)]:
            measurements[label] = {key: source[key] for key in ('samples', 'warmups', 'latency_ms', 'request_ms',
                'sql_queries_per_request', 'sql_duration_ms', 'client_process_cpu_seconds',
                'client_process_peak_rss_bytes', 'sequential_requests_per_second', 'response_sha256')}
            measurements[label]['median_sql_duration_ms'] = statistics.median(source['sql_duration_ms'])
        measurements['complete_response_equality'] = True
        result['endpoints'][name] = measurements
    for label in ['before', 'after']:
        result['browser_'+label] = json.loads((root/('optimization-browser-'+label+'.json')).read_text())
    def plan_nodes(node):
        allowed = ['Node Type', 'Index Name', 'Actual Rows', 'Actual Loops', 'Sort Method', 'Sort Space Used',
                   'Sort Space Type', 'Temp Read Blocks', 'Temp Written Blocks', 'Shared Hit Blocks', 'Shared Read Blocks']
        value = {key: node[key] for key in allowed if key in node}
        value['Plans'] = [plan_nodes(child) for child in node.get('Plans', [])]
        return value
    result['query_plans'] = [{'planning_ms': plan[0]['Planning Time'], 'execution_ms': plan[0]['Execution Time'],
                             'plan': plan_nodes(plan[0]['Plan'])} for plan in after['query_plans']]
    (root/'optimization-summary.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({name: {label: round(value[label]['median_sql_duration_ms'], 3) for label in ['before', 'after']}
                      for name, value in result['endpoints'].items()}))


if __name__ == '__main__':
    summarize(Path('/verification'))
