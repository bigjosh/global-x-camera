"""Render KiCad PDF for visual QA; does not author or alter the source PDF."""
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'tmp/schematic-review'
out.mkdir(parents=True,exist_ok=True)
doc=pdfium.PdfDocument(ROOT/'hardware/kicad/global-x-camera.pdf')
thumbs=[]
for i in range(len(doc)):
    im=doc[i].render(scale=1.75).to_pil().convert('RGB')
    im.save(out/f'page-{i+1:02}.png')
    im.thumbnail((620,440))
    canvas=Image.new('RGB',(640,470),'#eeeeee');canvas.paste(im,(10,22))
    ImageDraw.Draw(canvas).text((10,3),f'Page {i+1}',fill='black');thumbs.append(canvas)
for k in range(0,len(thumbs),6):
    c=Image.new('RGB',(1280,1410),'white')
    for j,t in enumerate(thumbs[k:k+6]):c.paste(t,((j%2)*640,(j//2)*470))
    c.save(out/f'contact-{k//6+1}.png')
print(f'Rendered {len(doc)} pages')
