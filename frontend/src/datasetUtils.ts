/**
 * datasetUtils.ts
 *
 * Non-component shared utilities and enterprise mock datasets
 * for the Enterprise Dataset Management Center.
 */

import type {
  Dataset,
  DatasetPreview,
  DatabaseConnection,
  ApiConnection,
  DataWarehouseCatalog,
  ColumnMetadata,
  DatasetProfileData,
  DatasetQualityData,
  DatasetVersionItem,
  DatasetLineageNode,
} from './types/datasets';

// ---------------------------------------------------------------------------
// 25 Enterprise Datasets matching user requirements
// ---------------------------------------------------------------------------

export const DEV_DATASETS: Dataset[] = [];

// ---------------------------------------------------------------------------
// Database Connections Mock Data
// ---------------------------------------------------------------------------

export const INITIAL_DB_CONNECTIONS: DatabaseConnection[] = [
  {
    id: 'conn-pg-prod',
    name: 'Production Analytics DB',
    engine: 'PostgreSQL',
    host: 'pg-prod.internal.cloud',
    port: 5432,
    database: 'enterprise_dw',
    username: 'etl_reader',
    ssl: true,
    status: 'connected',
    latencyMs: 14,
    tablesCount: 68,
    lastTestedAt: '2026-03-25T18:40:00Z',
  },
  {
    id: 'conn-mysql-store',
    name: 'E-Commerce Storefront',
    engine: 'MySQL',
    host: 'mysql-cluster.store.io',
    port: 3306,
    database: 'store_checkout',
    username: 'ro_analyst',
    ssl: true,
    status: 'connected',
    latencyMs: 28,
    tablesCount: 42,
    lastTestedAt: '2026-03-25T17:15:00Z',
  },
  {
    id: 'conn-mongo-events',
    name: 'Customer Events Store',
    engine: 'MongoDB',
    host: 'mongo-cluster.telemetry.net',
    port: 27017,
    database: 'user_activity',
    username: 'dw_ingest',
    ssl: true,
    status: 'connected',
    latencyMs: 19,
    tablesCount: 16,
    lastTestedAt: '2026-03-25T16:50:00Z',
  },
  {
    id: 'conn-sqlserver-erp',
    name: 'SAP ERP Financials',
    engine: 'SQL Server',
    host: 'sqlserver.corp.local',
    port: 1433,
    database: 'SAP_FIN_PROD',
    username: 'svc_bi_reader',
    ssl: false,
    status: 'connected',
    latencyMs: 35,
    tablesCount: 114,
    lastTestedAt: '2026-03-25T14:10:00Z',
  },
  {
    id: 'conn-oracle-core',
    name: 'Legacy Core Banking',
    engine: 'Oracle',
    host: 'oracle-rac.banking.internal',
    port: 1521,
    database: 'ORCL_MAIN',
    username: 'c##bi_user',
    ssl: true,
    status: 'connected',
    latencyMs: 42,
    tablesCount: 88,
    lastTestedAt: '2026-03-25T12:00:00Z',
  },
];

// ---------------------------------------------------------------------------
// API Connections Mock Data
// ---------------------------------------------------------------------------

export const INITIAL_API_CONNECTIONS: ApiConnection[] = [
  {
    id: 'api-stripe-billing',
    name: 'Stripe Billing API',
    type: 'REST API',
    baseUrl: 'https://api.stripe.com/v1',
    endpoint: '/invoices',
    authType: 'bearer',
    headers: [
      { key: 'Stripe-Version', value: '2024-06-20' },
      { key: 'Accept', value: 'application/json' },
    ],
    status: 'connected',
    latencyMs: 112,
    lastTestedAt: '2026-03-25T18:00:00Z',
  },
  {
    id: 'api-shopify-graphql',
    name: 'Shopify Storefront GraphQL',
    type: 'GraphQL API',
    baseUrl: 'https://storefront.myshopify.com/api/2026-01/graphql.json',
    authType: 'apiKey',
    apiKeyHeader: 'X-Shopify-Storefront-Access-Token',
    headers: [
      { key: 'Content-Type', value: 'application/json' },
    ],
    status: 'connected',
    latencyMs: 86,
    lastTestedAt: '2026-03-25T17:30:00Z',
  },
  {
    id: 'api-hubspot-crm',
    name: 'HubSpot Contacts & Deals',
    type: 'REST API',
    baseUrl: 'https://api.hubapi.com/crm/v3/objects',
    endpoint: '/deals',
    authType: 'bearer',
    headers: [
      { key: 'Content-Type', value: 'application/json' },
    ],
    status: 'connected',
    latencyMs: 135,
    lastTestedAt: '2026-03-25T15:20:00Z',
  },
];

// ---------------------------------------------------------------------------
// Data Warehouse Catalog Mock Data
// ---------------------------------------------------------------------------

export const INITIAL_WAREHOUSE_CATALOG: DataWarehouseCatalog = {
  factTables: [
    {
      id: 'fact-sales',
      name: 'fact_sales_transactions',
      description: 'Granular store and e-commerce checkout events with line-item totals and margins.',
      rowCount: 1_840_000,
      columnCount: 18,
      partitionKey: 'transaction_date (monthly)',
      sizeBytes: 420_000_000,
      lastRefreshed: '2026-03-25T18:00:00Z',
      columns: [
        { name: 'transaction_id', type: 'BIGINT', nullable: false, isPrimaryKey: true },
        { name: 'customer_id', type: 'BIGINT', nullable: false, isForeignKey: true },
        { name: 'product_id', type: 'BIGINT', nullable: false, isForeignKey: true },
        { name: 'transaction_date', type: 'DATE', nullable: false },
        { name: 'quantity', type: 'INTEGER', nullable: false },
        { name: 'unit_price', type: 'NUMERIC(12,2)', nullable: false },
        { name: 'gross_amount', type: 'NUMERIC(12,2)', nullable: false },
        { name: 'discount_amount', type: 'NUMERIC(12,2)', nullable: false },
        { name: 'net_amount', type: 'NUMERIC(12,2)', nullable: false },
        { name: 'tax_amount', type: 'NUMERIC(12,2)', nullable: false },
      ],
    },
    {
      id: 'fact-revenue',
      name: 'fact_monthly_revenue',
      description: 'Monthly ledger revenue recognition by cost center, region, and subscription cohort.',
      rowCount: 480_000,
      columnCount: 14,
      partitionKey: 'fiscal_period (quarterly)',
      sizeBytes: 110_000_000,
      lastRefreshed: '2026-03-25T12:00:00Z',
      columns: [
        { name: 'revenue_id', type: 'BIGINT', nullable: false, isPrimaryKey: true },
        { name: 'account_id', type: 'BIGINT', nullable: false, isForeignKey: true },
        { name: 'fiscal_period', type: 'VARCHAR(10)', nullable: false },
        { name: 'mrr_amount', type: 'NUMERIC(14,2)', nullable: false },
        { name: 'arr_equivalent', type: 'NUMERIC(14,2)', nullable: false },
      ],
    },
    {
      id: 'fact-churn',
      name: 'fact_customer_churn_events',
      description: 'Subscription cancellations, downgraded tiers, and voluntary retention loss.',
      rowCount: 64_000,
      columnCount: 12,
      partitionKey: 'cancellation_date',
      sizeBytes: 18_000_000,
      lastRefreshed: '2026-03-24T22:00:00Z',
      columns: [
        { name: 'churn_event_id', type: 'BIGINT', nullable: false, isPrimaryKey: true },
        { name: 'customer_id', type: 'BIGINT', nullable: false, isForeignKey: true },
        { name: 'lost_mrr', type: 'NUMERIC(10,2)', nullable: false },
        { name: 'churn_reason', type: 'VARCHAR(100)', nullable: true },
      ],
    },
  ],
  dimensionTables: [
    {
      id: 'dim-customers',
      name: 'dim_customers',
      description: 'SCD Type 2 dimension for customer attributes, tier, credit rating, and geography.',
      rowCount: 95_000,
      columnCount: 16,
      primaryKey: 'customer_id',
      sizeBytes: 34_000_000,
      lastRefreshed: '2026-03-25T16:00:00Z',
      columns: [
        { name: 'customer_id', type: 'BIGINT', nullable: false, isPrimaryKey: true },
        { name: 'customer_name', type: 'VARCHAR(255)', nullable: false },
        { name: 'tier', type: 'VARCHAR(50)', nullable: false },
        { name: 'industry', type: 'VARCHAR(100)', nullable: true },
        { name: 'country', type: 'VARCHAR(50)', nullable: false },
        { name: 'created_date', type: 'DATE', nullable: false },
      ],
    },
    {
      id: 'dim-products',
      name: 'dim_products',
      description: 'SKU definitions, product lines, manufacturer catalogs, and base prices.',
      rowCount: 24_000,
      columnCount: 12,
      primaryKey: 'product_id',
      sizeBytes: 8_500_000,
      lastRefreshed: '2026-03-25T08:00:00Z',
      columns: [
        { name: 'product_id', type: 'BIGINT', nullable: false, isPrimaryKey: true },
        { name: 'sku', type: 'VARCHAR(64)', nullable: false },
        { name: 'product_name', type: 'VARCHAR(255)', nullable: false },
        { name: 'category', type: 'VARCHAR(100)', nullable: false },
        { name: 'unit_cost', type: 'NUMERIC(10,2)', nullable: false },
      ],
    },
    {
      id: 'dim-regions',
      name: 'dim_regions',
      description: 'Global sales territories, operational warehouses, and currency locales.',
      rowCount: 120,
      columnCount: 8,
      primaryKey: 'region_id',
      sizeBytes: 52_000,
      lastRefreshed: '2026-03-20T00:00:00Z',
      columns: [
        { name: 'region_id', type: 'INTEGER', nullable: false, isPrimaryKey: true },
        { name: 'region_name', type: 'VARCHAR(100)', nullable: false },
        { name: 'currency_code', type: 'CHAR(3)', nullable: false },
      ],
    },
  ],
  views: [
    {
      id: 'v-high-value',
      name: 'v_high_value_customers',
      description: 'Logical view filtering accounts with lifetime spend > $100k and health score > 85.',
      sourceTables: ['dim_customers', 'fact_sales_transactions'],
      lastRefreshed: '2026-03-25T18:30:00Z',
      query: `SELECT c.customer_id, c.customer_name, c.tier, SUM(s.net_amount) AS ltv
FROM dim_customers c
JOIN fact_sales_transactions s ON c.customer_id = s.customer_id
GROUP BY c.customer_id, c.customer_name, c.tier
HAVING SUM(s.net_amount) >= 100000;`,
    },
    {
      id: 'v-quarterly-kpis',
      name: 'v_quarterly_kpis',
      description: 'Aggregated executive financial indicators computed on demand.',
      sourceTables: ['fact_monthly_revenue', 'fact_sales_transactions'],
      lastRefreshed: '2026-03-25T15:00:00Z',
      query: `SELECT fiscal_period, SUM(mrr_amount) AS total_mrr, COUNT(DISTINCT account_id) AS active_subscribers
FROM fact_monthly_revenue
GROUP BY fiscal_period;`,
    },
  ],
  materializedViews: [
    {
      id: 'mv-daily-sales',
      name: 'mv_daily_sales_aggregate',
      description: 'Pre-computed daily revenue, transaction count, and average order value.',
      refreshInterval: 'Every 1 Hour',
      lastRefreshed: '2026-03-25T18:00:00Z',
      rowCount: 1_250,
      sizeBytes: 2_400_000,
      query: `CREATE MATERIALIZED VIEW mv_daily_sales_aggregate AS
SELECT transaction_date, COUNT(*) as orders_count, SUM(net_amount) as daily_revenue, AVG(net_amount) as aov
FROM fact_sales_transactions
GROUP BY transaction_date;`,
      status: 'ready',
    },
    {
      id: 'mv-cohort-retention',
      name: 'mv_cohort_retention_matrix',
      description: 'Monthly customer cohort retention rates pre-calculated for instant visualization.',
      refreshInterval: 'Daily at 02:00 UTC',
      lastRefreshed: '2026-03-25T02:00:00Z',
      rowCount: 48,
      sizeBytes: 320_000,
      query: `CREATE MATERIALIZED VIEW mv_cohort_retention_matrix AS
SELECT cohort_month, tenure_month, active_users_pct
FROM analytics_engine.cohort_calculations;`,
      status: 'ready',
    },
  ],
};

// ---------------------------------------------------------------------------
// Dataset Previews (First 100 Records)
// ---------------------------------------------------------------------------

export const DEV_PREVIEWS: Record<string, DatasetPreview> = {};

// ---------------------------------------------------------------------------
// Dataset Deep Detail Helpers: Metadata, Profile, Quality, Lineage, Versions
// ---------------------------------------------------------------------------

export function getMockMetadata(datasetId: string): ColumnMetadata[] {
  if (datasetId === 'ds-customer-data') {
    return [
      { name: 'customer_id', datatype: 'String (UUID)', uniqueValues: 45000, nullCount: 0, nullPercentage: 0, sampleValues: ['CUST-5001', 'CUST-5002'], isPrimaryKey: true },
      { name: 'company_name', datatype: 'String', uniqueValues: 44920, nullCount: 0, nullPercentage: 0, sampleValues: ['Acme Labs', 'Nexus Corp'] },
      { name: 'industry', datatype: 'Categorical', uniqueValues: 8, nullCount: 120, nullPercentage: 0.27, sampleValues: ['FinTech', 'HealthTech'] },
      { name: 'tier', datatype: 'Categorical', uniqueValues: 4, nullCount: 0, nullPercentage: 0, sampleValues: ['Enterprise', 'Mid-Market'] },
      { name: 'annual_revenue', datatype: 'Numeric (Float)', uniqueValues: 38200, nullCount: 450, nullPercentage: 1.0, sampleValues: [120000, 480000] },
      { name: 'employee_count', datatype: 'Integer', uniqueValues: 1200, nullCount: 890, nullPercentage: 1.98, sampleValues: [50, 450] },
      { name: 'nps_score', datatype: 'Integer (1-10)', uniqueValues: 10, nullCount: 12, nullPercentage: 0.03, sampleValues: [8, 10] },
      { name: 'status', datatype: 'Categorical', uniqueValues: 3, nullCount: 0, nullPercentage: 0, sampleValues: ['Active', 'At Risk'] },
    ];
  }

  // Default to Sales_Data_2025 metadata
  return [
    { name: 'transaction_id', datatype: 'String (Alphanumeric)', uniqueValues: 15000, nullCount: 0, nullPercentage: 0, sampleValues: ['TXN-10001', 'TXN-10002'], isPrimaryKey: true },
    { name: 'date', datatype: 'DateTime (ISO)', uniqueValues: 365, nullCount: 0, nullPercentage: 0, sampleValues: ['2025-01-03', '2025-01-04'] },
    { name: 'customer_name', datatype: 'String', uniqueValues: 420, nullCount: 0, nullPercentage: 0, sampleValues: ['Acme Corp', 'Starlight Logistics'] },
    { name: 'region', datatype: 'Categorical', uniqueValues: 5, nullCount: 0, nullPercentage: 0, sampleValues: ['North America', 'EMEA', 'APAC'] },
    { name: 'product', datatype: 'Categorical', uniqueValues: 12, nullCount: 0, nullPercentage: 0, sampleValues: ['Enterprise Cloud', 'AI Analytics Pro'] },
    { name: 'quantity', datatype: 'Integer', uniqueValues: 45, nullCount: 0, nullPercentage: 0, sampleValues: [1, 5, 12] },
    { name: 'unit_price', datatype: 'Numeric (Float)', uniqueValues: 18, nullCount: 0, nullPercentage: 0, sampleValues: [850.0, 2400.0] },
    { name: 'total_amount', datatype: 'Numeric (Float)', uniqueValues: 4200, nullCount: 0, nullPercentage: 0, sampleValues: [4250.0, 12000.0] },
    { name: 'discount_rate', datatype: 'Percentage', uniqueValues: 8, nullCount: 42, nullPercentage: 0.28, sampleValues: [0.05, 0.15] },
    { name: 'profit_margin', datatype: 'Numeric (Float)', uniqueValues: 85, nullCount: 0, nullPercentage: 0, sampleValues: [0.65, 0.78], isTarget: true },
  ];
}

export function getMockProfile(_datasetId: string): DatasetProfileData {
  return {
    summary: {
      total_amount: {
        count: 15000,
        mean: 5840.50,
        median: 4800.00,
        stdDev: 2420.10,
        min: 850.00,
        max: 24800.00,
        q25: 3200.00,
        q75: 7800.00,
        distribution: [
          { bucket: '< $2k', count: 1840 },
          { bucket: '$2k - $5k', count: 5420 },
          { bucket: '$5k - $10k', count: 4980 },
          { bucket: '$10k - $15k', count: 1890 },
          { bucket: '> $15k', count: 870 },
        ],
        boxplot: { min: 850, q1: 3200, median: 4800, q3: 7800, max: 14700 },
      },
      quantity: {
        count: 15000,
        mean: 4.8,
        median: 4.0,
        stdDev: 2.9,
        min: 1,
        max: 35,
        q25: 2,
        q75: 7,
        distribution: [
          { bucket: '1 - 3 units', count: 5120 },
          { bucket: '4 - 6 units', count: 4890 },
          { bucket: '7 - 10 units', count: 3210 },
          { bucket: '11 - 20 units', count: 1420 },
          { bucket: '> 20 units', count: 360 },
        ],
        boxplot: { min: 1, q1: 2, median: 4, q3: 7, max: 14 },
      },
      profit_margin: {
        count: 15000,
        mean: 0.68,
        median: 0.70,
        stdDev: 0.12,
        min: 0.35,
        max: 0.92,
        q25: 0.60,
        q75: 0.78,
        distribution: [
          { bucket: '30% - 50%', count: 1240 },
          { bucket: '50% - 65%', count: 4210 },
          { bucket: '65% - 75%', count: 5890 },
          { bucket: '75% - 85%', count: 2840 },
          { bucket: '> 85%', count: 820 },
        ],
        boxplot: { min: 0.35, q1: 0.60, median: 0.70, q3: 0.78, max: 0.92 },
      },
    },
    correlation: {
      columns: ['Quantity', 'Unit Price', 'Total Amount', 'Discount', 'Margin'],
      matrix: [
        [1.00, -0.15, 0.78, 0.22, -0.32],
        [-0.15, 1.00, 0.62, -0.08, 0.54],
        [0.78, 0.62, 1.00, 0.14, 0.18],
        [0.22, -0.08, 0.14, 1.00, -0.68],
        [-0.32, 0.54, 0.18, -0.68, 1.00],
      ],
    },
  };
}

export function getMockQuality(_datasetId: string): DatasetQualityData {
  return {
    qualityScore: 92,
    missingValuesCount: 42,
    duplicateRowsCount: 0,
    outliersCount: 68,
    rules: [
      { rule: 'Primary Key Uniqueness', description: 'Zero duplicate transaction identifiers found', status: 'passed', score: 100 },
      { rule: 'Null Values Under Threshold', description: 'Missing values account for 0.02% of all entries', status: 'passed', score: 98 },
      { rule: 'Data Type Uniformity', description: 'All schema types match inferred columnar formats', status: 'passed', score: 96 },
      { rule: 'Numeric Range Integrity', description: 'Unit prices and amounts strictly non-negative', status: 'passed', score: 100 },
      { rule: 'Statistical Outlier Boundary', description: '68 transactions exceed 3x standard deviations on total_amount', status: 'warning', score: 84 },
      { rule: 'Date Sequence Continuity', description: 'Continuous daily distribution across FY2025 with no missing dates', status: 'passed', score: 95 },
    ],
  };
}

export function getMockVersions(_datasetId: string): DatasetVersionItem[] {
  return [
    {
      version_number: 3,
      label: 'Version 3 (Current Active)',
      created_at: '2026-03-20T14:15:00Z',
      author: 'Data Pipeline Engine',
      changelog: 'Feature engineering: Normalized profit margins and generated regional categorical groupings.',
      rows: 15_000,
      columns: 25,
      size_bytes: 4_850_000,
      isActive: true,
    },
    {
      version_number: 2,
      label: 'Version 2',
      created_at: '2026-02-18T10:00:00Z',
      author: 'Auto-Clean Agent',
      changelog: 'Data sanitization: Imputed 42 null discount values using median baseline; eliminated 6 duplicate test rows.',
      rows: 15_000,
      columns: 24,
      size_bytes: 4_720_000,
      isActive: false,
    },
    {
      version_number: 1,
      label: 'Version 1',
      created_at: '2026-01-15T08:30:00Z',
      author: 'User Ingestion',
      changelog: 'Initial raw upload of Sales_Data_2025.csv directly from S3 export bucket.',
      rows: 15_006,
      columns: 24,
      size_bytes: 4_910_000,
      isActive: false,
    },
  ];
}

export function getMockLineage(dataset: Dataset): DatasetLineageNode[] {
  return [
    {
      id: 'src-1',
      title: 'Data Source',
      type: 'source',
      description: `${dataset.filename} (${dataset.file_type})`,
      status: 'synced',
    },
    {
      id: 'raw-storage',
      title: 'Raw Storage',
      type: 'raw_storage',
      description: dataset.raw_path || `storage/raw/${dataset.filename}`,
      path: dataset.raw_path || `storage/raw/${dataset.filename}`,
      status: 'synced',
    },
    {
      id: 'engine-clean',
      title: 'Validation & Cleaning',
      type: 'engine',
      description: 'Schema parsing, null handling & profiling',
      status: 'active',
    },
    {
      id: 'processed-storage',
      title: 'Processed Storage',
      type: 'processed_storage',
      description: dataset.processed_path || `storage/processed/${dataset.name || 'data'}.parquet`,
      path: dataset.processed_path || `storage/processed/${dataset.name || 'data'}.parquet`,
      status: 'ready',
    },
    {
      id: 'registry',
      title: 'Dataset Registry',
      type: 'registry',
      description: 'metadata.json, profile.json, quality.json, lineage.json',
      status: 'ready',
    },
    {
      id: 'agent-eda',
      title: 'EDA Agent',
      type: 'ai_agent',
      description: 'Exploratory data analysis & automated statistical overview',
      status: 'ready',
    },
    {
      id: 'agent-sql',
      title: 'SQL Agent',
      type: 'ai_agent',
      description: 'Natural language text-to-SQL querying against warehouse',
      status: 'ready',
    },
    {
      id: 'agent-viz',
      title: 'Visualization Agent',
      type: 'ai_agent',
      description: 'Intelligent chart recommendation & visual dashboards',
      status: 'ready',
    },
    {
      id: 'agent-forecast',
      title: 'Forecast Agent',
      type: 'ai_agent',
      description: 'Prophet & XGBoost multi-step time series forecasting',
      status: 'ready',
    },
    {
      id: 'agent-insight',
      title: 'Insight Agent',
      type: 'ai_agent',
      description: 'Decision intelligence, causal drivers, and risk detection',
      status: 'ready',
    },
    {
      id: 'agent-recommendation',
      title: 'Recommendation Agent',
      type: 'ai_agent',
      description: 'Data hygiene suggestions & business action plans',
      status: 'ready',
    },
  ];
}

// ---------------------------------------------------------------------------
// Formatting Helpers
// ---------------------------------------------------------------------------

export const STATUS_LABELS: Record<string, string> = {
  ready:      'Ready',
  uploaded:   'Uploaded',
  validating: 'Validating',
  validated:  'Validated',
  processing: 'Processing',
  processed:  'Processed',
  failed:     'Failed',
  Ready:      'Ready',
  Processed:  'Processed',
};

export function formatFileSize(bytes: number): string {
  if (bytes < 1_024) return `${bytes} B`;
  if (bytes < 1_024 * 1_024) return `${(bytes / 1_024).toFixed(1)} KB`;
  if (bytes < 1_024 * 1_024 * 1_024)
    return `${(bytes / (1_024 * 1_024)).toFixed(1)} MB`;
  return `${(bytes / (1_024 * 1_024 * 1_024)).toFixed(2)} GB`;
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function getExtension(filename: string): string {
  const ext = filename.split('.').pop()?.toUpperCase() ?? '';
  return ext || '-';
}
