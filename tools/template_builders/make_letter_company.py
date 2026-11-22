import copy, sys
from docxlib import *
import lxml.etree as ET
d=Doc('/home/claude/work/tpl/letter_sample.docx'); b=d.body; ps=list(b)
# 1) header text box (two copies: DrawingML + VML fallback)
for tx in ps[0].iter(q('txbxContent')):
    p1,p2=tx.findall(q('p'))
    for p in (p1,p2):
        ppr=p.find(q('pPr')); sp=ppr.find(q('spacing'))
        if sp is None: sp=ET.Element(q('spacing')); ppr.insert(0,sp)
        sp.set(q('before'),'0'); sp.set(q('after'),'0'); sp.set(q('line'),'290'); sp.set(q('lineRule'),'exact')
    set_text(p1,'{{ date }}')
    pn=copy.deepcopy(p1); set_text(pn,'{{ number }}'); p1.addnext(pn)
    set_text(p2,'{{ attachment }}')
    # keep the same alignment for all three lines
    for p in (pn,p2):
        ppr=p.find(q('pPr')); jc=ppr.find(q('jc'))
        if jc is not None: ppr.remove(jc)
# 2) body
P3,P4,P5,P6,P7=ps[3],ps[4],ps[5],ps[6],ps[7]
set_text(P3,'{{ line }}')
P3.addprevious(tag_paragraph(P3,'{%p for line in addressee_lines %}'))
P3.addnext(tag_paragraph(P3,'{%p endfor %}'))
set_text(P4,'موضوع: {{ subject }}')
P4.addprevious(tag_paragraph(P4,'{%p if subject %}'))
P4.addnext(tag_paragraph(P4,'{%p endif %}'))
set_text(P5,'{{ salutation }}')
set_text(P6,'{{ para }}')
P6.addprevious(tag_paragraph(P6,'{%p for para in body_paragraphs %}'))
P6.addnext(tag_paragraph(P6,'{%p endfor %}'))
b.remove(P7)
# 3) signature block: closing text box + stamp/signature pictures (conditional)
P10=ps[10]
for tx in P10.iter(q('txbxContent')):
    for p in tx.findall(q('p')):
        rs=[r for r in p.findall(q('r')) if r.find(q('t')) is not None]
        if len(rs)>=2:
            rs[0].find(q('t')).text='{{ closing }} '; rs[-1].find(q('t')).text='{{ signer_name }}'
            for r in rs[1:-1]: p.remove(r)
NSR='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
for r in list(P10.findall(q('r'))):
    blips=[e.get('{%s}embed'%NSR) for e in r.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip')]
    if not blips: continue
    flag='show_stamp' if 'rId7' in blips else 'show_signature'
    r.addprevious(text_run_like(r,'{%% if %s %%}'%flag)); r.addnext(text_run_like(r,'{% endif %}'))
d.save(sys.argv[1])
