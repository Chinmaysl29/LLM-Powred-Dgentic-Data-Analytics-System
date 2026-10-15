import { useState } from 'react';
import type { ChartManifest } from '../../types/eda';

export function EDAChartCoordinates({ charts, onCategory }: { charts: ChartManifest[]; onCategory: (column: string, value: string) => void }) {
  const [selection, setSelection] = useState<Record<string,string>>({});
  return <>{(['histogram','scatter','time_series','grouped_bar'] as const).map(kind => {
    const options=charts.filter(c=>c.chart_type===kind);
    const chart=options.find(c=>c.chart_id===selection[kind]) ?? options[0];
    if (!chart) return null;
    const data=chart.coordinate_data;
    const xs=data.map((p,i)=>kind==='scatter'?Number(p.x):kind==='time_series'?Date.parse(String(p.timestamp)):i);
    const ys=data.map(p=>Number(kind==='histogram'?p.count:kind==='scatter'?p.y:p.value));
    const xmin=Math.min(...xs,0), xmax=Math.max(...xs,1), ymin=Math.min(...ys,0), ymax=Math.max(...ys,1);
    const x=(v:number)=>40+(v-xmin)/(xmax-xmin||1)*400;
    const y=(v:number)=>190-(v-ymin)/(ymax-ymin||1)*150;
    const width=400/Math.max(data.length,1);
    return <section key={kind} className="eda-card eda-span-6"><div className="eda-card-header"><div><p className="eda-card-eyebrow">{kind.replace('_',' ').toUpperCase()} / SOURCE COORDINATES</p><h2 className="eda-card-title">{chart.metric} by {chart.dimension}</h2></div></div>
      <div className="eda-card-body"><select aria-label={`${kind} chart`} value={chart.chart_id} onChange={e=>setSelection({...selection,[kind]:e.target.value})}>{options.map(c=><option key={c.chart_id} value={c.chart_id}>{c.metric} / {c.dimension}</option>)}</select>
      {!data.length?<p>No valid observations in this scope.</p>:<svg viewBox="0 0 480 240" role="img" aria-label={`${kind}: ${chart.metric} by ${chart.dimension}`} style={{width:'100%'}}>
      <line x1="40" x2="450" y1={y(0)} y2={y(0)} stroke="#718080"/><text x="4" y="35" fill="#c4d0c8" fontSize="10">{ymax.toLocaleString()}</text><text x="4" y="195" fill="#c4d0c8" fontSize="10">{ymin.toLocaleString()}</text>
      {kind==='time_series'&&<polyline fill="none" stroke="#D6FA43" strokeWidth="2" points={xs.map((v,i)=>`${x(v)},${y(ys[i])}`).join(' ')}/>}
      {data.map((p,i)=>kind==='scatter'||kind==='time_series'?<circle key={i} cx={x(xs[i])} cy={y(ys[i])} r="3" fill="#D6FA43"><title>{`${p.timestamp??p.x}: ${ys[i]}; source ${p.source_row??p.source_count}`}</title></circle>:<g key={i}>
        <rect x={40+i*width} y={Math.min(y(ys[i]),y(0))} width={Math.max(1,width-3)} height={Math.abs(y(ys[i])-y(0))} fill="#D6FA43" role={kind==='grouped_bar'?'button':undefined} tabIndex={kind==='grouped_bar'?0:undefined} aria-label={`${p.category??`${p.lower} to ${p.upper}`}: ${ys[i]}`} onClick={()=>kind==='grouped_bar'&&onCategory(chart.dimension,String(p.category))} onKeyDown={e=>{if(kind==='grouped_bar'&&(e.key==='Enter'||e.key===' ')){e.preventDefault();onCategory(chart.dimension,String(p.category));}}}><title>{`${p.category??`${p.lower} to ${p.upper}`}: ${ys[i]}`}</title></rect>
        {data.length<12&&<text x={40+i*width} y="215" fill="#c4d0c8" fontSize="9">{String(p.category??Number(p.lower).toPrecision(3)).slice(0,14)}</text>}</g>)}
      </svg>}
      <p>{chart.total_source_rows.toLocaleString()} source rows  ·  {chart.rendered_rows} marks  ·  {chart.aggregation}  ·  v{chart.version??'unversioned'}</p><p>{chart.sampling_method==='none'?'No row sampling':chart.sampling_method}. {chart.null_handling}.</p>{chart.warnings.map(w=><p key={w}>{w}</p>)}
      <details><summary>Provenance and exact coordinates</summary><pre style={{maxHeight:220,overflow:'auto',fontSize:10}}>{JSON.stringify(chart,null,2)}</pre></details></div></section>;
  })}</>;
}
