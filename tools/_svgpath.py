"""Minimal SVG path helpers: relative->absolute conversion, subpath split, bbox."""
import re
_TOK = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?')
_NPARAMS = {'M':2,'L':2,'H':1,'V':1,'C':6,'S':4,'Q':4,'T':2,'A':7,'Z':0}

def _tokens(d):
    out=[]
    for t in _TOK.findall(d):
        out.append(t if t.isalpha() else float(t))
    return out

def to_absolute(d):
    """Return path 'd' rewritten with absolute commands (M L C ... only as needed)."""
    toks=_tokens(d); i=0; out=[]; cx=cy=0.0; sx=sy=0.0; cmd=None
    def emit(c,*vals): out.append(c+" "+" ".join("%.4f"%v for v in vals))
    while i<len(toks):
        t=toks[i]
        if isinstance(t,str): cmd=t; i+=1
        rel=cmd.islower(); C=cmd.upper(); n=_NPARAMS[C]
        if C=='Z': emit('Z'); cx,cy=sx,sy; 
        else:
            p=toks[i:i+n]; i+=n
            if C=='M':
                x,y=p; 
                if rel: x+=cx; y+=cy
                emit('M',x,y); cx,cy=x,y; sx,sy=x,y; cmd='l' if rel else 'L'
            elif C=='L':
                x,y=p
                if rel:x+=cx;y+=cy
                emit('L',x,y);cx,cy=x,y
            elif C=='H':
                x=p[0]+(cx if rel else 0); emit('L',x,cy); cx=x
            elif C=='V':
                y=p[0]+(cy if rel else 0); emit('L',cx,y); cy=y
            elif C=='C':
                v=p[:]
                if rel: v=[v[0]+cx,v[1]+cy,v[2]+cx,v[3]+cy,v[4]+cx,v[5]+cy]
                emit('C',*v); cx,cy=v[4],v[5]
            elif C=='S':
                v=p[:]
                if rel: v=[v[0]+cx,v[1]+cy,v[2]+cx,v[3]+cy]
                emit('S',*v); cx,cy=v[2],v[3]
            elif C=='Q':
                v=p[:]
                if rel: v=[v[0]+cx,v[1]+cy,v[2]+cx,v[3]+cy]
                emit('Q',*v); cx,cy=v[2],v[3]
            elif C=='T':
                x,y=p
                if rel:x+=cx;y+=cy
                emit('T',x,y);cx,cy=x,y
            elif C=='A':
                v=p[:]
                if rel: v[5]+=cx; v[6]+=cy
                emit('A',*v); cx,cy=v[5],v[6]
        if C!='M' and isinstance(toks[i] if i<len(toks) else 0,(int,float)) and cmd.isupper()==False:
            pass
    return " ".join(out)

def split_subpaths(abs_d):
    """Split an absolute 'd' on each M into list of subpath 'd' strings."""
    parts=re.split(r'(?=M )', abs_d.strip())
    return [p.strip() for p in parts if p.strip()]

def bbox(abs_d):
    xs=[];ys=[]
    toks=_tokens(abs_d);i=0;cmd=None
    while i<len(toks):
        t=toks[i]
        if isinstance(t,str): cmd=t;i+=1;continue
        C=cmd.upper();n=_NPARAMS[C]
        p=toks[i:i+n];i+=n
        if C in('M','L','T'): xs.append(p[0]);ys.append(p[1])
        elif C=='C': xs+=[p[0],p[2],p[4]];ys+=[p[1],p[3],p[5]]
        elif C in('S','Q'): xs+=[p[0],p[2]];ys+=[p[1],p[3]]
        elif C=='A': xs.append(p[5]);ys.append(p[6])
    return (min(xs),min(ys),max(xs),max(ys))
