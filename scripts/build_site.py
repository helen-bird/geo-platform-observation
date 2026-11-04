#!/usr/bin/env python3
"""Rebuild public pages offline; optionally preserve evidence bytes for maintenance."""
import argparse,hashlib,io,json,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STAGES=['.', 'stages/02-post-discovery','stages/03-question-sensitivity','stages/04-creator-benchmark']

def strip_build_time(value):
    if isinstance(value,dict):return {k:strip_build_time(v)for k,v in value.items()if k!='generated_at'}
    if isinstance(value,list):return [strip_build_time(v)for v in value]
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preserve-evidence',action='store_true',help='Keep existing data/findings/archive bytes when doing a presentation-only update. Abort if scientific inputs/results change.');args=parser.parse_args()
    protected={}
    if args.preserve_evidence:
        for stage in STAGES:
            folder=ROOT/stage
            protected.update({p:p.read_bytes()for p in (folder/'data').rglob('*')if p.is_file()})
            protected.update({folder/n:(folder/n).read_bytes()for n in ('findings.json','public-data.zip')if(folder/n).is_file()})
    for name in ('rebuild.py','build_stage2_report.py','build_stage3_report.py','build_stage4_report.py','build_learning_hub.py','build_evidence_pages.py','build_sitemap.py'):
        subprocess.run([sys.executable,str(ROOT/'scripts'/name)],cwd=ROOT,check=True)
    if args.preserve_evidence:
        # Validate all newly computed results before restoring prior build timestamps.
        for p,old in protected.items():
            now=p.read_bytes()
            if p.name=='findings.json' and p.parent.name!='data':
                assert strip_build_time(json.loads(now))==strip_build_time(json.loads(old)),f'Scientific findings changed: {p.relative_to(ROOT)}'
            elif p.suffix=='.zip':
                with zipfile.ZipFile(io.BytesIO(old))as a,zipfile.ZipFile(io.BytesIO(now))as b:
                    assert set(a.namelist())==set(b.namelist()),f'Archive membership changed: {p.relative_to(ROOT)}'
                    for member in a.namelist():
                        x,y=a.read(member),b.read(member)
                        if member=='findings.json':assert strip_build_time(json.loads(x))==strip_build_time(json.loads(y))
                        else:assert x==y,f'Archived evidence changed: {member}'
            else:assert now==old,f'Evidence changed: {p.relative_to(ROOT)}'
        for p,old in protected.items():
            if p.read_bytes()!=old:p.write_bytes(old)
    print(json.dumps({'offline_build':'complete','evidence_files_preserved':len(protected),'paid_API_calls':0,'publication_performed':False}))

if __name__=='__main__':main()
