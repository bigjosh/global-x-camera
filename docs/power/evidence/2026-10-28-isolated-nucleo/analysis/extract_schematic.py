from pathlib import Path
from pypdf import PdfReader
p=Path('tmp/hardware-review/nucleo-modifications/mb1940-schematic.pdf')
r=PdfReader(p)
print('pages',len(r.pages))
out=Path('tmp/bringup/nucleo-isolated-20261028/analysis/schematic-text.txt')
text='\n\n'.join(f'PAGE {i+1}\n'+page.extract_text(extraction_mode='layout') for i,page in enumerate(r.pages))
out.write_text(text)
for i,page in enumerate(r.pages):
 t=page.extract_text()
 print(i+1,t[:120].replace('\n',' '))
