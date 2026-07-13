#!/usr/bin/env python3
"""Relivin short-video generator — animated vertical (1080x1920) motion cards.
make_short(style, tag, head, out_path) renders a ~5s branded Short via ffmpeg.
Styles: warm (gradient) / editorial (cream) / bold (plum). Fast: numpy bg + piped frames.
"""
import os, sys, math, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=1080,1920; FPS=30; DUR=5.0; N=int(FPS*DUR)
SR=44100  # audio sample rate
CORAL=(217,105,74); CORAL_DK=(178,74,46); PLUM=(91,75,110); CREAM=(246,241,234); INK=(43,37,33)

# ---- portable font resolution: local fonts/ dir first, then system, then DejaVu ----
FONT_DIRS=[os.environ.get("RELIVIN_FONT_DIR","fonts"),
           "/usr/share/fonts/truetype/google-fonts",
           "/usr/share/fonts/truetype/dejavu",
           "/usr/share/fonts/truetype/liberation"]
def _find(cands, fallback):
    for d in FONT_DIRS:
        for n in cands:
            p=os.path.join(d,n)
            if os.path.exists(p): return p
    for d in FONT_DIRS:
        fb=os.path.join(d,fallback)
        if os.path.exists(fb): return fb
    return fallback
LORA   =_find(["Lora-Variable.ttf","Lora[wght].ttf","Lora-Regular.ttf"],"DejaVuSerif.ttf")
LORA_IT=_find(["Lora-Italic-Variable.ttf","Lora-Italic[wght].ttf","Lora-Italic.ttf"],"DejaVuSerif-Italic.ttf")
P_BOLD =_find(["Poppins-Bold.ttf"],"DejaVuSans-Bold.ttf")
P_MED  =_find(["Poppins-Medium.ttf"],"DejaVuSans-Bold.ttf")
P_REG  =_find(["Poppins-Regular.ttf"],"DejaVuSans.ttf")
def F(p,s): return ImageFont.truetype(p,s)
def smooth(x): x=max(0.0,min(1.0,x)); return x*x*(3-2*x)
def seg(t,a,b): return smooth((t-a)/(b-a)) if b>a else (1.0 if t>=b else 0.0)

def _grad_np(w,h,c1,c2,angle=125):
    rad=math.radians(angle); dx,dy=math.cos(rad),math.sin(rad)
    xs=np.arange(w); ys=np.arange(h)
    proj=np.outer(ys,dy)+xs*dx
    lo,hi=proj.min(),proj.max(); tt=((proj-lo)/(hi-lo))[...,None]
    c1=np.array(c1); c2=np.array(c2)
    return (c1+(c2-c1)*tt).astype(np.uint8)

def _blob(size,cx,cy,rx,ry,color,alpha,blur):
    ov=Image.new("RGBA",size,(0,0,0,0)); d=ImageDraw.Draw(ov)
    d.ellipse([cx-rx,cy-ry,cx+rx,cy+ry],fill=color+(alpha,))
    return ov.filter(ImageFilter.GaussianBlur(blur))

def _bg(style):
    BW,BH=1220,2160
    if style=="warm":
        base=Image.fromarray(_grad_np(BW,BH,CORAL,PLUM,125))
        base=Image.alpha_composite(base.convert("RGBA"),_blob((BW,BH),380,470,300,300,(255,210,170),70,150))
        base=Image.alpha_composite(base,_blob((BW,BH),BW-420,BH-520,320,320,(70,50,90),80,150))
    elif style=="bold":
        base=Image.new("RGBA",(BW,BH),PLUM+(255,))
        base=Image.alpha_composite(base,_blob((BW,BH),BW-420,360,340,340,(150,120,175),90,150))
    else:
        base=Image.new("RGBA",(BW,BH),CREAM+(255,))
        base=Image.alpha_composite(base,_blob((BW,BH),150,150,360,360,(255,255,255),90,170))
        base=Image.alpha_composite(base,_blob((BW,BH),BW-150,BH-150,360,360,(220,205,188),80,170))
    return base.convert("RGB"),BW,BH

def _wrap(d,t,f,mw):
    out=[];cur=""
    for w in t.split():
        test=(cur+" "+w).strip()
        if d.textlength(test,font=f)<=mw: cur=test
        else:
            if cur:out.append(cur)
            cur=w
    if cur:out.append(cur)
    return out
def _ctext(d,y,text,font,rgb,alpha):
    w=d.textlength(text,font=font); d.text(((W-w)/2,y),text,font=font,fill=rgb+(int(alpha*255),))

# ---- original synthesized audio bed (100% generated -> no copyright / Content ID risk) ----
# Warm sine-based pad + soft bell shimmer. Chord differs per style so each Short varies.
_CHORDS={
 "warm":     [220.00,277.18,329.63,440.00],  # A major, warm
 "bold":     [196.00,246.94,293.66,392.00],  # G major, lower/fuller
 "editorial":[261.63,329.63,392.00,523.25],  # C major, brighter
}
def make_bed(style, path, dur=DUR):
    n=int(SR*dur); t=np.arange(n)/SR
    freqs=_CHORDS.get(style,_CHORDS["warm"])
    pad=np.zeros(n)
    for f in freqs:
        pad+=np.sin(2*np.pi*f*t)                 # fundamental
        pad+=0.35*np.sin(2*np.pi*f*1.004*t)      # detuned layer -> warmth
        pad+=0.22*np.sin(2*np.pi*f*0.5*t)        # sub octave -> body
    pad/=len(freqs)
    pad*=1.0+0.08*np.sin(2*np.pi*0.25*t)         # slow tremolo -> gentle movement
    bell=np.zeros(n)                              # soft bell arpeggio (octave up)
    for i,f in enumerate(freqs):
        start=0.6+i*(dur-1.0)/len(freqs)
        idx=t>=start; env=np.zeros(n); env[idx]=np.exp(-3.0*(t[idx]-start))
        bell+=0.22*env*np.sin(2*np.pi*f*2*t)
    mix=0.75*pad+0.35*bell
    mix*=np.clip(t/0.7,0,1)*np.clip((dur-t)/1.2,0,1)  # fade in / out
    mix/=(np.max(np.abs(mix))+1e-6); mix*=0.45         # normalize with headroom
    pcm=(mix*32767).astype(np.int16); stereo=np.column_stack([pcm,pcm]).ravel()
    with wave.open(path,"w") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(stereo.tobytes())
    return path

def make_short(style, tag, head, out_path):
    if style=="warm": hf=F(LORA,90); htxt=(255,252,248); ktxt=(255,236,224); wtxt=(255,250,246)
    elif style=="bold": hf=F(P_BOLD,84); htxt=(255,252,248); ktxt=(255,252,248); wtxt=(255,250,246)
    else: hf=F(LORA_IT,86); htxt=INK; ktxt=CORAL_DK; wtxt=INK
    fk=F(P_MED if style!="bold" else P_BOLD,32); fwb=F(P_BOLD,50); fwr=F(P_REG,28)
    BG,BW,BH=_bg(style)
    tmp=ImageDraw.Draw(Image.new("RGB",(10,10))); HL=_wrap(tmp,head,hf,880)
    ah,dh=hf.getmetrics(); lh=int((ah+dh)*(1.08 if style=="bold" else 1.14)); head_h=lh*len(HL); head_top=(H-head_h)//2-30
    bed=make_bed(style, out_path+".wav")
    proc=subprocess.Popen(["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
        "-i",bed,
        "-c:v","libx264","-pix_fmt","yuv420p","-profile:v","high","-crf","21",
        "-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",out_path],
        stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for i in range(N):
        t=i/FPS; p=i/(N-1)
        cw=int(BW-(BW-W)*p); ch=int(BH-(BH-H)*p); x0=(BW-cw)//2; y0=(BH-ch)//2
        fr=BG.crop((x0,y0,x0+cw,y0+ch)).resize((W,H),Image.BILINEAR).convert("RGBA")
        lay=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(lay)
        ka=seg(t,0.4,1.0); yk=head_top-100
        if ka>0:
            if style=="bold":
                tw=d.textlength(tag.upper(),font=fk); d.rounded_rectangle([W/2-tw/2-24,yk-8,W/2+tw/2+24,yk+50],radius=27,fill=CORAL+(int(ka*255),)); _ctext(d,yk+4,tag.upper(),fk,(255,252,248),ka)
            else:
                _ctext(d,yk,tag.upper(),fk,ktxt,ka); d.line([(W/2-46,yk+48),(W/2+46,yk+48)],fill=ktxt+(int(ka*255),),width=3)
        for li,line in enumerate(HL):
            st=1.0+li*0.32; la=seg(t,st,st+0.6)
            if la>0:
                off=int((1-smooth((t-st)/0.6))*26); _ctext(d,head_top+li*lh+off,line,hf,htxt,la)
        wa=seg(t,3.4,4.1); yw=H-230
        if wa>0: _ctext(d,yw,"Relivin",fwb,wtxt,wa); _ctext(d,yw+66,"relivin.app",fwr,wtxt,wa)
        proc.stdin.write(Image.alpha_composite(fr,lay).convert("RGB").tobytes())
    proc.stdin.close(); proc.wait()
    try: os.remove(bed)
    except OSError: pass
    return out_path

FEATURES=[
 ("warm","Timeline by age","Every moment, auto-sorted by age."),
 ("bold","Private by design","You choose exactly who sees it."),
 ("editorial","One shared timeline","Everyone’s photos, in one place."),
 ("warm","Notes & context","Save the story, not just the photo."),
 ("bold","Backed up for life","Every memory, safe for a lifetime."),
]
if __name__=="__main__":
    out=sys.argv[1] if len(sys.argv)>1 else "."
    os.makedirs(out,exist_ok=True)
    for i,(style,tag,head) in enumerate(FEATURES,1):
        make_short(style,tag,head,os.path.join(out,f"relivin_{i}.mp4")); print("made",f"relivin_{i}.mp4",f"({style})")
