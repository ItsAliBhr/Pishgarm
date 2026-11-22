"""Minimal docxtpl-compatible renderer used only to test templates here (real app uses docxtpl).
Supports {{ }}, {% %}, and the {%p ...%} / {%tr ...%} / {%tc ...%} / {%r ...%} paragraph/row/cell/run tags."""
import zipfile, re, sys, json, jinja2
def patch(xml):
    # join text split across runs inside tags (docxtpl does similar cleanup)
    def strip_tags(m): return re.sub(r'<[^>]+>','',m.group(0))
    xml=re.sub(r'\{[%{](?:(?!\{[%{]).)*?[%}]\}',lambda m: strip_tags(m),xml,flags=re.S)
    for tag,el in (('p','w:p'),('tr','w:tr'),('tc','w:tc'),('r','w:r')):
        pat=r'<%s[ >](?:(?!<%s[ >]).)*?\{%%\s*%s\s+(.*?)%%\}.*?</%s>'%(el,el,tag,el)
        xml=re.sub(pat,lambda m:'{% '+m.group(1)+' %}',xml,flags=re.S)
    return xml
def render(tpl,ctx,out):
    z=zipfile.ZipFile(tpl); files={n:z.read(n) for n in z.namelist()}
    env=jinja2.Environment(autoescape=True,undefined=jinja2.StrictUndefined)
    for n in files:
        if n.startswith('word/') and n.endswith('.xml') and ('document' in n or 'header' in n or 'footer' in n):
            x=patch(files[n].decode('utf8'))
            files[n]=env.from_string(x).render(**ctx).encode('utf8')
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as zo:
        for n,d in files.items(): zo.writestr(n,d)
if __name__=='__main__':
    render(sys.argv[1],json.load(open(sys.argv[2])),sys.argv[3])
