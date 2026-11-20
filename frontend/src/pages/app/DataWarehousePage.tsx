import { useEffect, useState } from 'react';
import { Database, Table2 } from 'lucide-react';
import { warehouseErrorMessage, warehouseService } from '../../services/warehouseService';
import type { WarehouseSchema } from '../../services/warehouseService';
export default function DataWarehousePage() {
  const [schema, setSchema] = useState<WarehouseSchema | null>(null);
  const [selected, setSelected] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    warehouseService
      .schema(controller.signal, attempt > 0)
      .then((data) => {
        if (!controller.signal.aborted) {
          setSchema(data);
          setSelected((previous) =>
            data.tables.some((t) => `${t.schema_name ?? ''}.${t.table_name}` === previous)
              ? previous
              : data.tables.length
                ? `${data.tables[0].schema_name ?? ''}.${data.tables[0].table_name}`
                : '',
          );
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(warehouseErrorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);
  const tables = schema?.tables ?? [];
  const table = tables.find((t) => `${t.schema_name ?? ''}.${t.table_name}` === selected);
  const namespaces = [...new Set(tables.map((t) => t.schema_name ?? 'Default schema'))];
  return (
    <div className="ws-page">
      <header className="editorial-heading">
        <p className="eyebrow">DATA MANAGEMENT / WAREHOUSE</p>
        <h1 className="ws-page-heading">Know the shape of your data.</h1>
        <p className="ws-page-sub">
          Read-only metadata from the configured database. Table counts are estimates where
          supplied.
        </p>
        <button
          className="reports-btn-secondary"
          disabled={loading}
          onClick={() => {
            setError('');
            setLoading(true);
            setAttempt((n) => n + 1);
          }}
        >
          Refresh schema
        </button>
      </header>
      {loading && <p role="status">Loading database schema…</p>}
      {error && (
        <div role="alert" className="surface-panel">
          <h2>Schema unavailable</h2>
          <p>{error}</p>
          <button
            className="reports-btn-secondary"
            onClick={() => {
              setError('');
              setLoading(true);
              setAttempt((n) => n + 1);
            }}
          >
            Retry schema
          </button>
        </div>
      )}
      {!schema && (
        <div className="warehouse-grid" aria-busy={loading}>
          <aside className="surface-panel warehouse-tree">
            <Database size={24} />
            <h2>Database explorer</h2>
            <p className="ws-page-sub">
              Tables and schemas appear here when metadata is available.
            </p>
          </aside>
          <section className="surface-panel warehouse-awaiting">
            <Table2 size={32} />
            <h2>{loading ? 'Discovering your schema' : 'Your table inspector'}</h2>
            <p className="ws-page-sub">
              Column definitions, row estimates and declared relationships are shown from the
              connected database.
            </p>
          </section>
        </div>
      )}
      {schema && !loading && !error && (
        <>
          <div className="source-note">
            <Database size={14} /> {schema.metadata.database_name || 'Configured database'} ·{' '}
            {schema.metadata.dialect} · {tables.length} tables ·{' '}
            {schema.metadata.is_cached ? 'Cached metadata' : 'Fresh metadata'}
          </div>
          <div className="warehouse-grid">
            <aside className="surface-panel warehouse-tree" aria-label="Database explorer">
              <label className="control-field">
                Find a table
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Table name"
                />
              </label>
              {namespaces.map((namespace) => (
                <details key={namespace} open>
                  <summary>{namespace}</summary>
                  {tables
                    .filter(
                      (t) =>
                        (t.schema_name ?? 'Default schema') === namespace &&
                        t.table_name.toLowerCase().includes(search.toLowerCase()),
                    )
                    .map((t) => {
                      const key = `${t.schema_name ?? ''}.${t.table_name}`;
                      return (
                        <button
                          key={key}
                          aria-pressed={selected === key}
                          onClick={() => setSelected(key)}
                        >
                          <Table2 size={14} /> {t.table_name}
                        </button>
                      );
                    })}
                </details>
              ))}
              {!tables.length && <p>No tables returned.</p>}
            </aside>
            <section className="surface-panel">
              {table ? (
                <>
                  <p className="eyebrow">TABLE SCHEMA</p>
                  <h2>{table.table_name}</h2>
                  {table.warnings?.map((warning, i) => (
                    <p role="status" key={i}>
                      {warning}
                    </p>
                  ))}
                  <p>
                    {table.columns.length} columns ·{' '}
                    {table.row_count_estimate == null
                      ? 'Row count unavailable'
                      : `Approximately ${table.row_count_estimate.toLocaleString()} rows`}
                  </p>
                  <div className="studio-values">
                    <table>
                      <caption>Column definitions</caption>
                      <thead>
                        <tr>
                          <th scope="col">Column</th>
                          <th scope="col">Type</th>
                          <th scope="col">Nullable</th>
                          <th scope="col">Key</th>
                        </tr>
                      </thead>
                      <tbody>
                        {table.columns.map((c) => (
                          <tr key={c.name}>
                            <th scope="row">{c.name}</th>
                            <td>{c.data_type}</td>
                            <td>{c.nullable ? 'Yes' : 'No'}</td>
                            <td>{c.primary_key ? 'Primary key' : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <h3>Indexes</h3>
                  {table.indexes?.length ? (
                    <ul>
                      {table.indexes.map((index, i) => (
                        <li key={index.name ?? i}>
                          <strong>{index.name ?? 'Unnamed index'}</strong>
                          {index.unique ? ' · Unique' : ''}
                          <ol>
                            {(index.keys?.length
                              ? index.keys
                              : index.columns.map((column_name, position) => ({
                                  position,
                                  kind: 'column' as const,
                                  column_name,
                                  expression: null,
                                  sorting: [],
                                }))
                            ).map((key) => (
                              <li key={key.position}>
                                <code>
                                  {key.kind === 'column'
                                    ? key.column_name
                                    : key.kind === 'expression'
                                      ? key.expression
                                      : 'Unknown index key'}
                                </code>
                                {key.kind === 'expression' ? ' (expression)' : ''}
                                {key.sorting.length ? ` · ${key.sorting.join(' ')}` : ''}
                              </li>
                            ))}
                          </ol>
                          {!!index.include_columns?.length && (
                            <p>Include: {index.include_columns.join(', ')}</p>
                          )}
                          {index.predicate && (
                            <p>
                              Where: <code>{index.predicate}</code>
                            </p>
                          )}
                          {typeof index.dialect_options?.postgresql_using === 'string' && (
                            <p>Method: {index.dialect_options.postgresql_using}</p>
                          )}
                          {index.warnings?.map((warning, j) => (
                            <p role="status" key={j}>
                              {warning}
                            </p>
                          ))}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No index information returned.</p>
                  )}
                  <h3>Unique constraints</h3>
                  {table.unique_constraints?.length ? (
                    <ul>
                      {table.unique_constraints.map((constraint, i) => (
                        <li key={constraint.name ?? i}>
                          {constraint.name ?? 'Unnamed constraint'}: {constraint.columns.join(', ')}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No unique constraints returned.</p>
                  )}
                  <h3>Relationships</h3>
                  {table.foreign_keys.length ? (
                    <ul>
                      {table.foreign_keys.map((r, i) => (
                        <li key={i}>
                          {r.source_columns.join(', ')} → {r.target_table} (
                          {r.target_columns.join(', ')})
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No outbound foreign keys returned.</p>
                  )}
                  <p className="source-note">
                    This schema API returns metadata only. Row previews and query execution are not
                    exposed here.
                  </p>
                </>
              ) : (
                <p>Select a table to inspect its columns and relationships.</p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
