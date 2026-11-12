"""Reproducible application icon, drawn from basic shapes."""
from pathlib import Path
from PIL import Image, ImageDraw

root=Path(__file__).resolve().parent
(root/'assets').mkdir(exist_ok=True)
im=Image.new('RGBA',(256,256),(0,0,0,0))
d=ImageDraw.Draw(im)
d.rounded_rectangle((4,4,252,252),radius=54,fill='#1762db')
d.polygon([(69,39),(148,39),(189,80),(189,214),(69,214)],fill='white')
d.polygon([(147,39),(147,81),(189,81)],fill='#bcd5fa')
d.rounded_rectangle((88,100,163,108),radius=4,fill='#abc4e5')
d.rounded_rectangle((88,119,151,127),radius=4,fill='#abc4e5')
d.line((101,145,120,164,101,183),fill='#1762db',width=10)
d.line((158,145,139,164,158,183),fill='#1762db',width=10)
im.save(root/'assets'/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
