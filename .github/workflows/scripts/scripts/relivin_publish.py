#!/usr/bin/env python3
"""Relivin weekly social pipeline — runs inside GitHub Actions.

  1. Generates this ISO week's 5 on-brand cards (rotating styles + content bank).
  2. Posts each to the Upload-Post queue via the REST API (direct file upload —
     no public image host required).
  3. Auto-prunes archived card folders older than --prune-days.

Env:
  UPLOAD_POST_API_KEY  (required for --post)  your Upload-Post API key
  RELIVIN_PROFILE      default "Relivin"       Upload-Post profile name
  RELIVIN_PLATFORMS    default "instagram,facebook"
  RELIVIN_FONT_DIR     default "fonts"         where brand fonts live

Usage:
  python relivin_publish.py --post --prune-days 30
  python relivin_publish.py --dry-run          # generate + show payloads, no posting
"""
import sys, os, math, json, datetime, argparse, shutil

from PIL import Image, ImageDraw, ImageFont, ImageFilter

INK=(43,37,33); CREAM=(246,241,234); CORAL=(217,105,74); CORAL_DK=(178,74,46); PLUM=(91,75,110)
S=1080

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
SERIF    =_find(["Lora-Variable.ttf","Lora[wght].ttf","Lora-Regular.ttf"],"DejaVuSerif.ttf")
SERIF_IT =_find(["Lora-Italic-Variable.ttf","Lora-Italic[wght].ttf","Lora-Italic.ttf"],"DejaVuSerif-Italic.ttf")
SANS_BOLD=_find(["Poppins-Bold.ttf"],"DejaVuSans-Bold.ttf")
SANS_MED =_find(["Poppins-Medium.ttf"],"DejaVuSans-Bold.ttf")
SANS_REG =_find(["Poppins-Regular.ttf"],"DejaVuSans.ttf")
def F(p,s): return ImageFont.truetype(p,s)

def gradient(c1,c2,angle=140):
    base=Image.new("RGB",(S,S),c1); top=Image.new("RGB",(S,S),c2); mask=Image.new("L",(S,S)); md=mask.load()
    rad=math.radians(angle); dx,dy=math.cos(rad),math.sin(rad)
    projs=[x*dx+y*dy for x,y in [(0,0),(S,0),(0,S),(S,S)]]; lo,hi=min(projs),max(projs)
    for y in range(S):
        ry=y*dy
        for x in range(0,S,2):
            v=int((x*dx+ry-lo)/(hi-lo)*255); md[x,y]=v
            if x+1<S: md[x+1,y]=v
    return Image.composite(top,base,mask)
def blob(img,cx,cy,r,color,alpha=60):
    ov=Image.new("RGBA",(S,S),(0,0,0,0)); d=ImageDraw.Draw(ov)
    d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=color+(alpha,)); ov=ov.filter(ImageFilter.GaussianBlur(r//2))
    return Image.alpha_composite(img.convert("RGBA"),ov).convert("RGB")
def wrap(d,t,f,mw):
    out=[]; cur=""
    for w in t.split():
        test=(cur+" "+w).strip()
        if d.textlength(test,font=f)<=mw: cur=test
        else:
            if cur: out.append(cur)
            cur=w
    if cur: out.append(cur)
    return out
def bh(t,f,mw,lg=1.16):
    d=ImageDraw.Draw(Image.new("RGB",(10,10))); a,de=f.getmetrics()
    return int((a+de)*lg)*len(wrap(d,t,f,mw))
def block(img,t,f,fill,mw,cx,ty,lg=1.16):
    d=ImageDraw.Draw(img); a,de=f.getmetrics(); lh=int((a+de)*lg); y=ty
    for ln in wrap(d,t,f,mw):
        w=d.textlength(ln,font=f); d.text((cx-w/2,y),ln,font=f,fill=fill); y+=lh
    return y
def heart(d,cx,cy,s,color):
    r=s/3.4
    d.ellipse([cx-r*1.5,cy-r,cx-r,cy+r*0.2],fill=color); d.ellipse([cx,cy-r,cx+r*1.5,cy+r*0.2],fill=color)
    d.polygon([(cx-r*1.42,cy-r*0.1),(cx+r*1.42,cy-r*0.1),(cx,cy+r*1.7)],fill=color)
def wordmark(img,color,y=980):
    d=ImageDraw.Draw(img); f=F(SANS_BOLD,40)
    d.text(((S-d.textlength("Relivin",font=f))/2,y),"Relivin",font=f,fill=color)
    fs=F(SANS_REG,22); d.text(((S-d.textlength("relivin.app",font=fs))/2,y+52),"relivin.app",font=fs,fill=color)
def st_warm(h,tag):
    img=gradient(CORAL,PLUM,140); img=blob(img,200,180,320,(255,210,170),70); img=blob(img,950,950,380,(70,50,90),60)
    d=ImageDraw.Draw(img); fk=F(SANS_MED,26)
    d.text(((S-d.textlength(tag.upper(),font=fk))/2,150),tag.upper(),font=fk,fill=(255,236,224))
    d.line([(S/2-40,194),(S/2+40,194)],fill=(255,236,224),width=2)
    fh=F(SERIF,76); h2=bh(h,fh,820); block(img,h,fh,(255,252,248),820,S/2,(S-h2)/2-20); wordmark(img,(255,250,246)); return img
def st_editorial(h,tag):
    img=Image.new("RGB",(S,S),CREAM); d=ImageDraw.Draw(img); d.rectangle([54,54,S-54,S-54],outline=(211,196,178),width=2)
    fk=F(SANS_MED,24); d.text(((S-d.textlength(tag.upper(),font=fk))/2,168),tag.upper(),font=fk,fill=CORAL_DK)
    fh=F(SERIF_IT,82); h2=bh(h,fh,800,1.14); y=block(img,h,fh,INK,800,S/2,(S-h2)/2-10,1.14)
    d.line([(S/2-46,y+30),(S/2+46,y+30)],fill=CORAL,width=3); wordmark(img,INK); return img
def st_bold(h,tag):
    img=Image.new("RGB",(S,S),PLUM); img=blob(img,900,160,300,(150,120,175),80); d=ImageDraw.Draw(img)
    fk=F(SANS_BOLD,24); tw=d.textlength(tag.upper(),font=fk)
    d.rounded_rectangle([S/2-tw/2-22,150,S/2+tw/2+22,202],radius=26,fill=CORAL); d.text((S/2-tw/2,162),tag.upper(),font=fk,fill=(255,252,248))
    fh=F(SANS_BOLD,84); h2=bh(h,fh,860,1.08); block(img,h,fh,(255,252,248),860,S/2,(S-h2)/2-10,1.08); wordmark(img,(255,250,246)); return img
STYLES={"warm":st_warm,"editorial":st_editorial,"bold":st_bold}
CTA="Join the waitlist → relivin.app"; TAGS="#Relivin #FamilyMemories #Parenthood #Keepsake"

BANK=[
 ("warm","Timeline by age","Every moment, auto-sorted by age.",
  "Relivin files every photo and video onto one timeline, automatically organized by age. Jump straight to “age 2” or “first steps” — no folders, no endless scrolling."),
 ("bold","Private by design","You choose exactly who sees it.",
  "Relivin is invite-only by design. Add the grandparents, the godparents, the people who were actually there — and no one else. No public profile, no followers, no strangers."),
 ("editorial","One shared timeline","Everyone’s photos, in one place.",
  "The best photo of the day is usually on someone else’s phone. Relivin lets everyone who was there add to the same private timeline, so the whole story lives in one place."),
 ("warm","Notes & context","Save the story, not just the photo.",
  "Add a note to any memory — what they said, where you were, why it mattered. Relivin keeps the context that camera rolls and captions lose."),
 ("bold","Backed up for life","Every memory, safe for a lifetime.",
  "Phones break and feeds vanish. Relivin keeps every photo, video, and note in one secure, private home — backed up and built to last a lifetime."),
]

def generate(out):
    os.makedirs(out,exist_ok=True)
    wk=datetime.date.today().isocalendar()[1]
    start=((wk-1)%3)*5
    picks=[BANK[(start+i)%len(BANK)] for i in range(5)]
    items=[]
    for i,(style,tag,head,body) in enumerate(picks,1):
        img=STYLES[style](head,tag)
        fn=f"relivin_w{wk:02d}_{i}_{style}.png"; p=os.path.join(out,fn); img.save(p,"PNG")
        items.append({"file":fn,"path":p,"style":style,"caption":f"{body}\n\n{CTA}\n\n{TAGS}"})
        print("generated",fn)
    return items

def post_to_queue(item, profile, platforms, dry=False):
    import requests
    key=os.environ.get("UPLOAD_POST_API_KEY","")
    data=[("user",profile),("title",item["caption"]),("add_to_queue","true")]
    for pf in platforms: data.append(("platform[]",pf))
    if dry:
        print(f"  [dry-run] POST /api/upload_photos  user={profile} platforms={platforms} file={item['file']}")
        return {"dry_run":True}
    if not key:
        print("  ! UPLOAD_POST_API_KEY not set — skipping post"); return {"skipped":True}
    with open(item["path"],"rb") as fh:
        files=[("photos[]",(item["file"],fh,"image/png"))]
        r=requests.post("https://api.upload-post.com/api/upload_photos",
                        headers={"Authorization":f"Apikey {key}"},
                        data=data, files=files, timeout=180)
    ok = r.status_code<300
    print(f"  {'queued' if ok else 'FAILED'} {item['file']} -> HTTP {r.status_code} {r.text[:160]}")
    return {"status":r.status_code,"ok":ok}

def prune(root, days):
    if not os.path.isdir(root): return
    cutoff=datetime.date.today()-datetime.timedelta(days=days)
    for name in sorted(os.listdir(root)):
        p=os.path.join(root,name)
        if not os.path.isdir(p): continue
        try: d=datetime.date.fromisoformat(name)
        except ValueError: continue
        if d<cutoff:
            shutil.rmtree(p); print("pruned",p)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--post",action="store_true")
    ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--prune-days",type=int,default=30)
    ap.add_argument("--root",default="social")
    a=ap.parse_args()

    profile=os.environ.get("RELIVIN_PROFILE","Relivin")
    platforms=[x.strip() for x in os.environ.get("RELIVIN_PLATFORMS","instagram,facebook").split(",") if x.strip()]

    today=datetime.date.today().isoformat()
    out=os.path.join(a.root,today)
    items=generate(out)
    # captions archive
    with open(os.path.join(out,"captions.json"),"w") as f: json.dump(
        [{"file":i["file"],"style":i["style"],"caption":i["caption"]} for i in items], f, indent=2, ensure_ascii=False)

    cur=os.path.join(a.root,"current"); os.makedirs(cur,exist_ok=True)
    for k,it in enumerate(items,1):
        shutil.copy(it["path"], os.path.join(cur,f"relivin_{k}.png"))
    json.dump([{"file":f"relivin_{k}.png","style":it["style"],"caption":it["caption"]} for k,it in enumerate(items,1)],
              open(os.path.join(cur,"cards.json"),"w"), indent=2, ensure_ascii=False)

    if a.post or a.dry_run:
        print(f"Posting {len(items)} cards to queue (profile={profile}, platforms={platforms})…")
        for it in items: post_to_queue(it, profile, platforms, dry=a.dry_run)

    prune(a.root, a.prune_days)
    print("done:", today)

if __name__=="__main__": main()
