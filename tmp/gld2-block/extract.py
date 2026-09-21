import zipfile, io, json, re, pathlib, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'output/diagrams/gld2'; OUT.mkdir(parents=True,exist_ok=True)
archive=ROOT/'docs/wiring/gld-project-ver2-2026-07-01/source-GLD2.zip'
z=zipfile.ZipFile(archive); n=zipfile.ZipFile(io.BytesIO(z.read(z.namelist()[0])))
s=json.loads(n.read('1-Schematic_MotherBoardGLDVer1.json'))
p=json.loads(n.read('1-PCB_PCB_MotherBoardGLDVer1.json'))
components={}
for sheet in s['schematics']:
 for shape in sheet['dataStr']['shape']:
  if not shape.startswith('LIB~'): continue
  parts=shape.split('#@$'); texts=[x.split('~') for x in parts if x.startswith('T~')]
  ref=next((x[12] for x in texts if x[1]=='P'),None)
  val=next((x[12] for x in texts if x[1]=='N'),None)
  if not ref or ref=='A': continue
  pins={}
  for part in parts:
   if part.startswith('P~'):
    a=part.split('^^'); pin=a[4].split('~')[4]; name=a[3].split('~')[4]
    pins[pin]={'name':name,'xy':a[1],'net':None}
  components[ref]={'value':val,'sheet':sheet['title'],'xy':parts[0].split('~')[1:3],'pins':pins}
for shape in p['shape']:
 if not shape.startswith('LIB~'): continue
 parts=shape.split('#@$'); ref=next((x.split('~')[10] for x in parts if x.startswith('TEXT~P~')),None)
 if ref not in components: continue
 for x in parts:
  if x.startswith('PAD~'):
   a=x.split('~'); pin=a[8]; net=a[7]
   if pin in components[ref]['pins']: components[ref]['pins'][pin]['net']=net
# Independently trace schematic wires and labels. Connections use pin/label/wire
# endpoints lying on wire segments; a bare crossing does not create a junction.
parent={}; labels=[]; segments=[]
def pt(a): return tuple(round(float(x),4) for x in a)
def find(x):
 parent.setdefault(x,x)
 if parent[x]!=x: parent[x]=find(parent[x])
 return parent[x]
def union(a,b): parent[find(a)]=find(b)
for c in components.values():
 for v in c['pins'].values(): find(pt(v['xy'].split('~')))
for sheet in s['schematics']:
 for x in sheet['dataStr']['shape']:
  a=x.split('~')
  if x.startswith('W~'):
   coords=a[1].split(); pts=[pt(coords[i:i+2]) for i in range(0,len(coords),2)]
   for a,b in zip(pts,pts[1:]): segments.append((a,b)); union(a,b)
  elif x.startswith('N~'): labels.append((pt(a[1:3]),a[5])); find(labels[-1][0])
  elif x.startswith('F~'):
   f=x.split('^^'); labels.append((pt(f[1].split('~')),f[2].split('~')[0])); find(labels[-1][0])
  elif x.startswith('J~'): find(pt(a[1:3]))
for a,b in segments:
 for q in list(parent):
  cross=(q[0]-a[0])*(b[1]-a[1])-(q[1]-a[1])*(b[0]-a[0])
  if abs(cross)<1e-5 and min(a[0],b[0])-1e-5<=q[0]<=max(a[0],b[0])+1e-5 and min(a[1],b[1])-1e-5<=q[1]<=max(a[1],b[1])+1e-5: union(a,q)
names={}
for q,name in labels: names.setdefault(find(q),set()).add(name)
mismatches=[]
for ref,c in components.items():
 for pin,v in c['pins'].items():
  v['schematic_labels']=sorted(names.get(find(pt(v['xy'].split('~'))),set()))
  if v['schematic_labels'] and v['net'] not in v['schematic_labels']: mismatches.append([ref,pin,v['net'],v['schematic_labels']])
data={'archive':str(archive.relative_to(ROOT)),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'sheets':[x['title'] for x in s['schematics']],'components':components,'named_net_mismatches':mismatches}
(OUT/'source-net-evidence.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
lines=[]
for ref,c in components.items():
 lines.append(ref+' '+str(c['value'])+' | '+', '.join(k+':'+v['name']+'='+str(v['net']) for k,v in c['pins'].items()))
(ROOT/'tmp/gld2-block/inventory.txt').write_text('\n'.join(lines),encoding='utf8')
print('Sheets:',data['sheets'],'Components:',len(components),'SHA:',data['sha256'])
print('Named-net mismatches:',mismatches)

