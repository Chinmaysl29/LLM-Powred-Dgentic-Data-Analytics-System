"""Bounded render coordinates computed from a complete authorized source scope."""
from itertools import combinations
import numpy as np
import pandas as pd
from backend.app.schemas.eda import ChartManifest


def build_charts(df, dataset_id=None, **provenance):
    charts = []
    numeric = list(df.select_dtypes(include=[np.number]).columns)[:12]
    dates = [c for c in df if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in str(c).lower() for k in ('date', 'timestamp'))][:2]
    categories = [c for c in df if c not in numeric and c not in dates][:4]
    def emit(kind, metric, dimension, aggregation, coordinates, **metadata):
        sampling = metadata.pop('sampling_method', 'none')
        warnings = metadata.pop('warnings', [])
        charts.append(ChartManifest(chart_id=f'{kind}:{dimension}:{metric}', chart_type=kind,
            dataset_id=dataset_id, metric=metric, dimension=dimension, aggregation=aggregation,
            total_source_rows=len(df), rendered_rows=len(coordinates), coordinate_data=coordinates,
            sampling_method=sampling, computation_metadata=metadata, warnings=warnings, **provenance))
    for col in numeric:
        values = pd.to_numeric(df[col], errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
        counts, edges = np.histogram(values, bins=min(30, max(1, int(np.ceil(np.sqrt(len(values))))))) if len(values) else ([], [])
        emit('histogram', col, col, 'count', [dict(lower=float(edges[i]), upper=float(edges[i+1]), count=int(n)) for i,n in enumerate(counts)],
             valid_observations=len(values), null_count=len(df)-len(values), bin_rule='sqrt capped at 30', interval='left closed; final bin right closed')
    for x,y in list(combinations(numeric, 2))[:12]:
        pairs = df[[x,y]].replace([np.inf,-np.inf], np.nan).dropna()
        selected = pairs
        method='none'
        if len(pairs)>1000:
            positions = set(np.linspace(0,len(pairs)-1,996,dtype=int).tolist())
            for col in (x,y):
                positions.update([int(np.argmin(pairs[col].to_numpy())),int(np.argmax(pairs[col].to_numpy()))])
            selected=pairs.iloc[sorted(positions)]; method='deterministic evenly spaced rows plus axis extrema; at most 1000'
        emit('scatter', y, x, 'none', [dict(x=float(a),y=float(b),source_row=str(idx)) for idx,a,b in selected.itertuples(name=None)],
            sampling_method=method, valid_pairs=len(pairs), excluded_rows=len(df)-len(pairs),
            x_domain=[float(pairs[x].min()),float(pairs[x].max())] if len(pairs) else [], y_domain=[float(pairs[y].min()),float(pairs[y].max())] if len(pairs) else [])
    for date in dates:
        timestamps=pd.to_datetime(df[date],errors='coerce',utc=True,format='mixed')
        for metric in numeric[:4]:
            pairs=pd.DataFrame({'timestamp':timestamps,'value':df[metric]}).replace([np.inf,-np.inf],np.nan).dropna()
            grouped=pairs.groupby('timestamp',sort=True)['value'].agg(['sum','count'])
            # Aggregate all records; cap rendered groups without fabricating absent periods.
            frequency='exact timestamp'
            if len(grouped)>1000:
                grouped=pairs.set_index('timestamp')['value'].resample('MS').agg(['sum','count']); grouped=grouped[grouped['count']>0]; frequency='month start'
            emit('time_series',metric,date,'sum',[dict(timestamp=t.isoformat(),value=float(row['sum']),source_count=int(row['count'])) for t,row in grouped.iterrows()],
                 timezone='UTC; naive timestamps interpreted UTC',frequency=frequency,missing_periods='omitted; never zero-filled',invalid_rows=len(df)-len(pairs),duplicate_timestamp_rows=len(pairs)-pairs['timestamp'].nunique())
    for category in categories:
        for metric in numeric[:4]:
            pairs=df[[category,metric]].replace([np.inf,-np.inf],np.nan).dropna().copy()
            pairs[category]=pairs[category].astype(str)
            groups=pairs.groupby(category,sort=True)[metric].sum()
            # Complete totals are retained in metadata when high-cardinality output is bounded.
            selected=groups.sort_values(ascending=False,kind='stable').head(30)
            emit('grouped_bar',metric,category,'sum',[dict(category=str(k),value=float(v)) for k,v in selected.items()],
                 category_count=len(groups),total=float(groups.sum()),omitted_total=float(groups.sum()-selected.sum()),
                 warnings=['Top 30 categories; omitted category total in metadata'] if len(groups)>30 else [])
    return charts

