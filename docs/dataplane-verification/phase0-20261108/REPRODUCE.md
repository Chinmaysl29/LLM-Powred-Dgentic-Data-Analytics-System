# Phase 0 reproduction commands

Run from C:\data analyst in PowerShell. Requires the existing backend/frontend images and Docker. These commands use synthetic data and a separate Compose project; no application storage or .env is mounted into the benchmark.

The benchmark deliberately records a child-process OOM to establish a limit. Its 1/2 GiB container cap and disabled swap protect the rest of the stack. Do not increase the budget without first checking Docker's available allocation.

## Backend baseline

~~~powershell
docker compose -p dataanalyst-dataplane-audit -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/dataplane-phase0-baseline.xml
~~~

Actual output: 334 passed, 5 warnings in 257.39s. The runner upgrades the isolated test schema; it does not target the live database.

## Frontend baseline

~~~powershell
@'
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const excluded=new Set(['node_modules','dist','.git','.ui-review']);
fs.cpSync('/source','/tmp/audit',{recursive:true,filter:p=>!path.relative('/source',p).split(path.sep).some(x=>excluded.has(x))});
fs.cpSync('/app/node_modules','/tmp/audit/node_modules',{recursive:true});
for(const task of ['typecheck','build']){const r=spawnSync('npm',['run',task],{cwd:'/tmp/audit',stdio:'inherit'});if(r.status!==0)process.exit(r.status??1);}
'@ | docker run --rm -i --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --env npm_config_cache=/tmp/npm-cache --entrypoint node dataanalyst-frontend:latest -
~~~

Actual output: typecheck exit 0; build exit 0, Vite 8.3.6, 2,374 modules, 2.22s.

## Benchmark harness

The following is the complete inline Python harness used. It writes only into the isolated verification volume. Each run gets a new directory; input and generated artifacts from earlier runs are not overwritten.

~~~powershell
$benchmarkScript = @'
import csv, hashlib, json, os, pathlib, subprocess, sys, time, uuid
root=pathlib.Path("/verification/benchmark")/("phase0-"+uuid.uuid4().hex[:10])
root.mkdir(parents=True)
worker=r'''
import hashlib,json,pathlib,resource,sys,time
mode,source,destination=sys.argv[1:]
started=time.perf_counter()
if mode=="materialize":
    from backend.app.core.config import Settings
    from backend.app.services.storage_service import StorageService
    from backend.app.services.dataset_json_service import DatasetJsonService
    service=DatasetJsonService(StorageService(Settings(_env_file=None,upload_dir=destination)))
    result=service.materialize("synthetic","synthetic",source,"csv")
    result["artifact_bytes"]=sum(p.stat().st_size for p in pathlib.Path(destination).rglob("*") if p.is_file())
else:
    from backend.app.services.tabular_loader import load_tabular_dataframe
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    frame=load_tabular_dataframe(source,"csv")
    result=NaturalLanguageAnalyticsService()._execute("sum amount_cents by region",frame)
print(json.dumps({"seconds":time.perf_counter()-started,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,"result":result},default=str))
'''
def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def events():
    try:return dict(line.split() for line in pathlib.Path("/sys/fs/cgroup/memory.events").read_text().splitlines())
    except OSError:return {}
all_results=[]
for count in [100_000,250_000,500_000,1_000_000,2_000_000]:
    source=root/f"synthetic-{count}.csv"
    expected={r:0 for r in ["east","west","north","south"]}
    with source.open("w",newline="") as f:
        writer=csv.writer(f);writer.writerow(["row_id","account_id","region","order_date","amount_cents"])
        regions=list(expected)
        for i in range(count):
            region=regions[i%4];amount=i%10000
            expected[region]+=amount
            writer.writerow([i,f"acct_{i:010d}",region,f"2026-01-{1+i%28:02d}",amount])
    before=digest(source)
    failed=False
    for mode in ["analytics","materialize"]:
        out=root/f"{count}-{mode}.stdout";err=root/f"{count}-{mode}.stderr"
        prior=events();peak=0;timed_out=False;started=time.perf_counter()
        with out.open("w") as stdout,err.open("w") as stderr:
            process=subprocess.Popen([sys.executable,"-c",worker,mode,str(source),str(root/f"output-{count}")],stdout=stdout,stderr=stderr)
            while process.poll() is None:
                try:
                    for line in pathlib.Path(f"/proc/{process.pid}/status").read_text().splitlines():
                        if line.startswith("VmRSS:"):peak=max(peak,int(line.split()[1])*1024)
                except (OSError,ProcessLookupError):pass
                if time.perf_counter()-started>120:
                    timed_out=True;process.kill();break
                time.sleep(0.025)
            process.wait()
        after=events()
        record={"mode":mode,"rows":count,"source_bytes":source.stat().st_size,"source_sha256":before,
                "expected_region_sums":expected,"source_unchanged":digest(source)==before,
                "exit_code":process.returncode,"timed_out":timed_out,"wall_seconds":round(time.perf_counter()-started,3),
                "sampled_peak_rss_bytes":peak,"oom_kill_delta":int(after.get("oom_kill",0))-int(prior.get("oom_kill",0))}
        lines=out.read_text().strip().splitlines()
        if process.returncode==0 and lines:
            try:record["measurement"]=json.loads(lines[-1])
            except ValueError:record["stdout_tail"]=lines[-3:]
        else:record["stderr_tail"]=err.read_text()[-2500:]
        all_results.append(record)
        (root/"results.json").write_text(json.dumps({"memory_limit_bytes":1073741824,"cpus":2,"sample_interval_ms":25,"results":all_results},indent=2))
        print(json.dumps(record),flush=True)
        if process.returncode!=0:failed=True
    if failed:break
print(json.dumps({"evidence_directory":str(root)}),flush=True)

'@
$benchmarkScript | docker run --rm -i --name dataanalyst-dataplane-benchmark --memory 1g --memory-swap 1g --cpus 2 --network none --read-only --tmpfs /tmp:rw,size=64m --mount 'type=volume,source=dataanalyst-dataplane-audit_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst,target=/repo,readonly' --workdir /tmp --env PYTHONPATH=/repo --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --env JWT_SECRET_KEY=isolated-phase0-benchmark-only-123456789 --entrypoint python dataanalyst-backend:latest -
~~~

The second run used the identical harness with the following two replacements and the 2 GiB cap:

~~~powershell
$benchmarkScript2 = $benchmarkScript.Replace('[100_000,250_000,500_000,1_000_000,2_000_000]', '[500_000,1_000_000,2_000_000]').Replace('"memory_limit_bytes":1073741824', '"memory_limit_bytes":2147483648')
$benchmarkScript2 | docker run --rm -i --name dataanalyst-dataplane-benchmark --memory 2g --memory-swap 2g --cpus 2 --network none --read-only --tmpfs /tmp:rw,size=64m --mount 'type=volume,source=dataanalyst-dataplane-audit_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst,target=/repo,readonly' --workdir /tmp --env PYTHONPATH=/repo --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --env JWT_SECRET_KEY=isolated-phase0-benchmark-only-123456789 --entrypoint python dataanalyst-backend:latest -
~~~

Wait for each command to finish; do not run these concurrently with the test suite. Actual evidence directories were phase0-88cc6dd671 and phase0-878d2cca33. A replay generates different directory suffixes but identical CSV bytes/hashes.

## Evidence export used for this run

The target directory was newly created for this audit. Do not overwrite unrelated evidence when reproducing; use a new date/run directory.

~~~powershell
New-Item -ItemType Directory -Path 'docs/dataplane-verification/phase0-20261108' -Force | Out-Null
docker create --name dataanalyst-dataplane-evidence --network none --read-only --mount 'type=volume,source=dataanalyst-dataplane-audit_verify_storage,target=/verification,readonly' --entrypoint python dataanalyst-backend:latest -c pass
docker cp dataanalyst-dataplane-evidence:/verification/dataplane-phase0-baseline.xml docs/dataplane-verification/phase0-20261108/backend-baseline.xml
docker cp dataanalyst-dataplane-evidence:/verification/benchmark/phase0-88cc6dd671/results.json docs/dataplane-verification/phase0-20261108/pandas-1g.json
docker cp dataanalyst-dataplane-evidence:/verification/benchmark/phase0-878d2cca33/results.json docs/dataplane-verification/phase0-20261108/pandas-2g.json
docker rm dataanalyst-dataplane-evidence
~~~

## Independent result validation

The following validation was executed after exporting both JSON files. It checks all successful analytics answers against integer oracles, verifies stored Parquet metadata, confirms source hashes and confirms the two kernel OOM events.

~~~powershell
@'
import json,pathlib,hashlib,xml.etree.ElementTree as ET
root=pathlib.Path("/evidence")
out={"backend":{},"benchmarks":[]}
xml=ET.parse(root/"backend-baseline.xml").getroot()
suites=list(xml.iter("testsuite"))
out["backend"]={k:sum(int(s.get(k,"0")) for s in suites) for k in ("tests","failures","errors","skipped")}
for name in ("pandas-1g.json","pandas-2g.json"):
    payload=json.loads((root/name).read_text())
    for r in payload["results"]:
        assert r["source_unchanged"]
        good=r["exit_code"]==0
        check={"budget_gib":payload["memory_limit_bytes"]/2**30,"mode":r["mode"],"rows":r["rows"],"input_mib":round(r["source_bytes"]/2**20,3),"wall_seconds":r["wall_seconds"],"source_unchanged":True,"outcome":"success" if good else "oom_killed"}
        if good:
            m=r["measurement"];check["peak_rss_mib"]=round(m["peak_rss_bytes"]/2**20,3)
            if r["mode"]=="analytics":
                result=m["result"]
                assert result["status"]=="complete"
                assert {row["region"]:row["amount_cents"] for row in result["data"]}==r["expected_region_sums"]
                assert result["kpis"]["count"]==r["rows"]
                assert result["kpis"]["total"]==sum(r["expected_region_sums"].values())
                check["exact_aggregate_oracle_passed"]=True
            else:
                result=m["result"]
                assert result["row_count"]==r["rows"] and result["canonical_format"]=="parquet"
                assert result["content_hash"]==r["source_sha256"]
                import pyarrow.parquet as pq
                assert pq.read_metadata(result["canonical_path"]).num_rows==r["rows"]
                check["parquet_metadata_verified"]=True
                check["artifact_mib"]=round(result["artifact_bytes"]/2**20,3)
        else:
            assert r["exit_code"]==-9 and r["oom_kill_delta"]==1 and not r["timed_out"]
            check["cgroup_oom_confirmed"]=True
        out["benchmarks"].append(check)
out["artifact_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
(root/"verified-summary.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))

'@ | docker run --rm -i --network none --read-only --memory 256m --memory-swap 256m --env PYTHONDONTWRITEBYTECODE=1 --mount 'type=volume,source=dataanalyst-dataplane-audit_verify_storage,target=/verification,readonly' --mount 'type=bind,source=C:\data analyst\docs\dataplane-verification\phase0-20261108,target=/evidence' --entrypoint python dataanalyst-backend:latest -
~~~

Actual result: exit 0; six exact aggregate oracle checks passed; four Parquet metadata/hash checks passed; two OOM kills confirmed; all 12 source-immutability checks passed. Artifact hashes in verified-summary.json refer to the exported baseline/benchmark evidence present when validation ran.

## Stop test infrastructure without deleting volumes

~~~powershell
docker compose -p dataanalyst-dataplane-audit -f docker-compose.verify.yml stop
docker compose ps --format '{{.Service}} {{.Status}}'
~~~

The isolated services were stopped after the suite and before the 2 GiB benchmark. All five live services remained healthy. No global cleanup, application restart or volume deletion was performed.

