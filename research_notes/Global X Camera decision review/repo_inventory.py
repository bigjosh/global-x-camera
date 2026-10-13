from pathlib import Path
import json, hashlib, collections, re
ROOT=Path('D:/Github/global-x-camera')
OUT=ROOT/'research_notes/Global X Camera decision review'
rows=[]; hashes={}; authored=[]; json_summaries=[]; script_summaries=[]; pdf_summaries=[]
try:
 import fitz
except ImportError: fitz=None
from pypdf import PdfReader
for p in sorted(ROOT.rglob('*')):
 if not p.is_file() or p.relative_to(ROOT).parts[0] in ('imports','research_notes','reports','.git'): continue
 rel=p.relative_to(ROOT).as_posix(); data=p.read_bytes(); sha=hashlib.sha256(data).hexdigest(); ext=p.suffix.lower()
 row=dict(path=str(p).replace('\\','/'),relative_path=rel,bytes=len(data),sha256=sha)
 if sha in hashes: row['duplicate_of']=hashes[sha]
 else: hashes[sha]=rel
 if '.git' in p.parts:
  row['coverage']='embedded KiCad save-history metadata/object inventory; history log inspected separately; not semantic source'
 elif ext in ('.md','.txt','.py','.json','.kicad_mod','.kicad_sch','.kicad_pro','.kicad_prl','.kicad_sym','.xml','.edif','.html','.svg','.c','.h','.gitignore','.sha256',''):
  try: txt=data.decode('utf-8-sig'); row['lines']=len(txt.splitlines())
  except UnicodeError: txt=data.decode('utf-8',errors='replace'); row['decode_replacements']=txt.count('\ufffd')
  if ext=='.md': row['coverage']='project authored narrative, semantic review'; authored.append(rel)
  elif ext=='.json':
   row['coverage']='structured JSON parsed; review/source/validation fields inspected'
   try:
    obj=json.loads(txt); row['json_top_keys']=list(obj)[:25] if isinstance(obj,dict) else f'list length {len(obj)}'
    if not rel.endswith('.source.json') and not any(x in rel for x in ('pads.json','native-components.json','schematic-connectivity','kicad-readable/validation','connectivity.json')):
     json_summaries.append(dict(path=rel,top=row['json_top_keys'], excerpt=txt[:5000] if len(txt)<15000 else txt[:1500]))
   except Exception as e: row['parse_error']=str(e)
  elif ext=='.py':
   row['coverage']='script text statically indexed for purpose/constants/comments; not executed'
   script_summaries.append(dict(path=rel,head='\n'.join(txt.splitlines()[:35]),markers=[(i,l) for i,l in enumerate(txt.splitlines(),1) if re.search(r'(?i)(decision|assum|recommend|TODO|FIXME|override|inferred|unresolved|provisional)',l)][:25]))
  elif ext in ('.kicad_mod','.kicad_sch','.kicad_sym','.kicad_pro','.kicad_prl','.xml','.edif') or rel.endswith(('fp-lib-table','sym-lib-table')):
   row['coverage']='generated CAD/netlist text structurally indexed; evidence via reconciliation/validation and targeted current-net checks'
   row['reference_count']=len(re.findall(r'\(property "Reference"',txt)); row['pad_count']=len(re.findall(r'\(pad ',txt))
  elif ext in ('.txt','.c','.h'):
   row['coverage']='vendor datasheet extract or reference-driver evidence indexed; source requirements checked via project reviews' if rel!='bom.txt' else 'original BOM semantic and part-count review'
  elif ext in ('.html','.svg'): row['coverage']='source/download page or generated diagram structurally indexed; narrative counterpart reviewed'
  else: row['coverage']='supporting text inventory'
 elif ext=='.pdf':
  row['coverage']='PDF identity/page count inspected; vendor reference, not project decision; relevant evidence via linked reviews'
  if fitz:
   try:
    doc=fitz.open(p); row['pages']=len(doc); row['title']=doc.metadata.get('title'); first=' '.join(doc[0].get_text().split())[:1200] if len(doc) else ''; pdf_summaries.append(dict(path=rel,pages=len(doc),first_page=first)); doc.close()
   except Exception as e: row['parse_error']=str(e)
  else:
   try:
    doc=PdfReader(p); row['pages']=len(doc.pages); row['title']=doc.metadata.title if doc.metadata else None; first=' '.join((doc.pages[0].extract_text() or '').split())[:1200] if len(doc.pages) else ''; pdf_summaries.append(dict(path=rel,pages=len(doc.pages),first_page=first))
   except Exception as e: row['parse_error']=str(e)
 elif ext=='.png': row['coverage']='supporting render/screenshot inventory; dimensions inspected, not all images visually re-reviewed'
 elif ext=='.pyc': row['coverage']='compiled Python cache; duplicate implementation excluded from semantic decisions'
 else: row['coverage']='binary/supporting asset inventory only'
 if ext=='.png':
  try:
   from PIL import Image
   with Image.open(p) as img: row['dimensions']=list(img.size)
  except Exception as e: row['parse_error']=str(e)
 rows.append(row)
(OUT/'repository-file-manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
(OUT/'repository-json-index.json').write_text(json.dumps(json_summaries,indent=2),encoding='utf-8')
(OUT/'repository-script-index.json').write_text(json.dumps(script_summaries,indent=2),encoding='utf-8')
(OUT/'repository-pdf-index.json').write_text(json.dumps(pdf_summaries,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(rows),bytes=sum(x['bytes'] for x in rows),extensions=dict(collections.Counter(Path(x['relative_path']).suffix for x in rows)),top_folders=dict(collections.Counter(x['relative_path'].split('/')[0] for x in rows)),duplicates=sum('duplicate_of' in x for x in rows),pdf_pages=sum(x.get('pages',0) for x in rows),errors=[(x['relative_path'],x['parse_error']) for x in rows if 'parse_error' in x]),indent=2))
