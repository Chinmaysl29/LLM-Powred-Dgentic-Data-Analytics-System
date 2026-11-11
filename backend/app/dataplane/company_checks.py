"""Bounded health checks with no application service or database imports."""
from datetime import datetime, timezone

def health_checks(engine, rules, used):
    """Full-snapshot SQL checks inside the bounded child, never API memory."""
    from backend.app.dataplane.semantic import quote
    checks = []
    for index, rule in enumerate(rules):
        col = quote(rule['column'])
        item = {'rule': rule, 'rule_version': 1, 'id': f'rule:{index}', 'coverage': 'full',
            'collected_at': datetime.now(timezone.utc).isoformat(), 'field': rule['column'],
            'impact': 'directly_affected' if rule['column'] in used else 'unaffected',
            'impact_reason': 'Recorded required field lineage', 'expected': 0}
        if rule['column'] not in engine.schema():
            item.update(status='failed', observed='missing_required_field')
        else:
            if rule['check'] == 'not_null':
                sql, args = f'SELECT COUNT(*) FROM source WHERE {col} IS NULL', []
            elif rule['check'] == 'unique':
                sql, args = f'SELECT COUNT(*)-COUNT(DISTINCT {col}) FROM source', []
            else:
                clauses, args = [], []
                for key, operator in (('minimum', '<'), ('maximum', '>')):
                    if rule.get(key) is not None:
                        clauses.append(f'{col} {operator} ?')
                        args.append(rule[key])
                sql = f'SELECT COUNT(*) FROM source WHERE ' + ' OR '.join(clauses)
            try:
                observed = engine.connection.execute(sql, args).fetchone()[0]
                item.update(status='passed' if observed == 0 else 'failed', observed=observed)
            except Exception:
                item.update(status='error', observed=None)
        item['blocks'] = item['status'] != 'passed' and rule['severity'] == 'critical' and rule['column'] in used
        checks.append(item)
    return checks


