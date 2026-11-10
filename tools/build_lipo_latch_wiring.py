"""Shared SVG/PNG drawing primitives and compatibility entry point for the complete LiPo/USB circuit.

No instruments are accessed. Requires Pillow; labels use Windows Segoe UI.
"""
from pathlib import Path
import html
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/power'
W, H, SCALE = 1800, 1260, 2
INK, POWER, CTRL, GND, MUTED = '#1c3044', '#b13b35', '#136b9b', '#526474', '#5d7080'

class Drawing:
    def __init__(self):
        self.im = Image.new('RGB', (W*SCALE,H*SCALE), 'white')
        self.d = ImageDraw.Draw(self.im)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                    '<title>SPDT capacitor trigger and PD7 LiPo power-hold wiring</title>',
                    '<rect width="100%" height="100%" fill="white"/>']
    def text(self,x,y,s,size=22,color=INK,bold=False):
        font=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size*SCALE)
        self.d.text((x*SCALE,y*SCALE),s,font=font,fill=color,anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y+size*.84}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(s)}</text>')
    def line(self,pts,color=CTRL,width=3):
        self.d.line([(x*SCALE,y*SCALE) for x,y in pts],fill=color,width=width*SCALE)
        self.svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="none" stroke="{color}" stroke-width="{width}"/>')
    def rect(self,x,y,w,h,fill='#f4f8fb',color=CTRL):
        self.d.rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),fill=fill,outline=color,width=2*SCALE)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="2"/>')
    def dot(self,x,y,color=CTRL,r=5):
        self.d.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill=color)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')
    def resistor_h(self,x1,x2,y,label,color=CTRL):
        mid=(x1+x2)/2
        self.line([(x1,y),(mid-40,y)],color)
        self.rect(mid-40,y-12,80,24,'white',color)
        self.line([(mid+40,y),(x2,y)],color)
        self.text(mid-75,y-47,label,21,color,True)
    def ground(self,x,y):
        self.line([(x,y),(x,y+12)],GND)
        for dy,half in [(12,16),(20,10),(28,4)]:self.line([(x-half,y+dy),(x+half,y+dy)],GND,2)
    def capacitor_h(self,x1,x2,y,label):
        mid=(x1+x2)/2
        self.line([(x1,y),(mid-6,y)])
        self.line([(mid+6,y),(x2,y)])
        self.line([(mid-6,y-18),(mid-6,y+18)])
        self.line([(mid+6,y-18),(mid+6,y+18)])
        self.text(mid-55,y+22,label,21,CTRL,True)
    def resistor_v(self,x,y1,y2):
        mid=(y1+y2)/2
        self.line([(x,y1),(x,mid-32)])
        self.rect(x-12,mid-32,24,64,'white',CTRL)
        self.line([(x,mid+32),(x,y2)])
    def contact(self,x,y):
        r=7
        self.d.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill='white',outline=CTRL,width=3*SCALE)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="white" stroke="{CTRL}" stroke-width="3"/>')

c=Drawing()
# Keep this entry point for existing documentation and scripts. Other power
# drawings reuse the primitives above without executing this rendering step.
if __name__ == '__main__':
    import runpy
    runpy.run_path(str(ROOT / 'tools/build_lipo_usb_power_wiring.py'), run_name='__main__')
