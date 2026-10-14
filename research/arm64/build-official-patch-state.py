#!/usr/bin/env python3
"""Build only the DS124 72806 official persistent flash-backup state in work/."""
import importlib.util,logging,json,hashlib,tarfile,io
from pathlib import Path
w=Path(__file__).resolve().parent/'work'
assert hashlib.sha256((w/'extracted/updater').read_bytes()).hexdigest() == '9d207ec7156abc1f70ab5970e2a53606cbc31a1b3e02ea30bbc3bf55c7c49c32', 'Evidence is specific to DS124 72806 updater'
# Addresses and exclusion table are proven in updater-disassembly.txt; never run the updater against host devices.
logging.disable(logging.CRITICAL)
spec=importlib.util.spec_from_file_location('patology',w/'patology.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OctalHeaders(m.Synocrack):
 def _decode_header_field(self, tarinfo, field, value, needs_atol=False):
  if field == 'mode':
   tarinfo.mode=int(value.decode().split('\x00')[0],8)
   return tarinfo
  return super()._decode_header_field(tarinfo,field,value,needs_atol)
with (w/'DSM_DS124_72806.pat').open('rb') as f:pat=OctalHeaders(f)
exclude={'hda1.tgz','indexdb.txz','synohdpack_img.txz','checksum.syno','Synology.sig','updater_manutil','createvolume','SkipCheckPackingMatch','autonano.pat','RedBoot.msys','configupdate'}
rows=[];chosen=[]
for name,entry in pat.entries.items():
 h=entry['header'];data=entry['entry'];path=w/'extracted'/name
 assert path.read_bytes()==data,name
 rows.append(dict(path=name,mode=oct(h.mode),uid=h.uid,gid=h.gid,size=len(data),sha256=hashlib.sha256(data).hexdigest(),type=str(h.type)))
 if '/' not in name and h.isfile() and name not in exclude:chosen.append(name)
checksum=pat.entries['checksum.syno']['entry']
# Exact grep -i <filename> checksum.syno in the official backup loop, once for each selected entry.
lines=checksum.splitlines(keepends=True)
filtered=b''.join(line for name in chosen for line in lines if name.lower().encode() in line.lower())
(w/'patch-analysis/pat-metadata.json').write_text(json.dumps(rows,indent=2)+'\n')
(w/'patch-analysis/official-backup-selection.json').write_text(json.dumps(dict(selected=chosen,excluded=sorted(exclude),checksum=filtered.decode(),operation='updater backup loop cp -rf source staging; grep -i filename checksum.syno >> /tmp/checksum.syno.recover; cp -af recover staging/checksum.syno; swap staging into .syno/patch'),indent=2)+'\n')
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/platform'))
from arm_contract import patch_archive
patch_archive({name: (entry['header'], entry['entry']) for name, entry in pat.entries.items()},
              w/'patch-analysis/official-patch-state.tar')
print('Verified every decrypted PAT entry against existing extraction.')
print('Official backup selection:',chosen)
print('Selected original metadata:',[r for r in rows if r['path'] in chosen])
