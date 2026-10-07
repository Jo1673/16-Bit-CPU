#!/usr/bin/env python3
"""Collect ORFS evidence for review. File presence never certifies signoff."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('orfs_root',type=Path)
p.add_argument('-o','--output',type=Path,default=Path('cpu16_orfs_results.zip'))
a=p.parse_args()
flow=a.orfs_root.expanduser().resolve()/'flow'
if not (flow/'Makefile').is_file(): p.error('expected ORFS repository root (parent of flow)')
files=[]
for folder in ('results','reports','logs'):
    directory=flow/folder/'sky130hd/cpu16_core/base'
    if directory.exists(): files.extend(x for x in directory.rglob('*') if x.is_file())
for folder in ('designs/src/cpu16_core','designs/sky130hd/cpu16_core'):
    directory=flow/folder
    if directory.exists(): files.extend(x for x in directory.rglob('*') if x.is_file())
if not any('/results/' in str(f) for f in files): p.error('no physical-design results found')
try:
    commit=subprocess.check_output(['git','-C',str(a.orfs_root),'rev-parse','HEAD'],text=True).strip()
except subprocess.CalledProcessError: commit='unknown'
manifest={'orfs_commit':commit,'signoff':'NOT CERTIFIED; inspect reports and complete docs/TAPEOUT.md',
          'files':{str(f.relative_to(flow)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}}
with zipfile.ZipFile(a.output,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(files): z.write(f,str(f.relative_to(flow)))
    z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
print(f'Collected {len(files)} files into {a.output}; this is evidence collection, not signoff approval.')
