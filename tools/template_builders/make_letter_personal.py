import sys, docx
from docx.shared import Pt, Cm, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
d=docx.Document(); s=d.sections[0]
s.page_width=Mm(210); s.page_height=Mm(297); s.left_margin=s.right_margin=Cm(2.5); s.top_margin=Cm(2); s.bottom_margin=Cm(2)
st=d.styles['Normal']; st.font.size=Pt(13); st.font.name='B Nazanin'
rpr=st.element.get_or_add_rPr(); rf=rpr.find(qn('w:rFonts'))
for a in ('ascii','hAnsi','cs','eastAsia'): rf.set(qn('w:'+a),'B Nazanin')
sz=OxmlElement('w:szCs'); sz.set(qn('w:val'),'26'); rpr.append(sz)
def P(text,align='right',bold=False,size=None,space_after=6,line=None,indent=None):
    p=d.add_paragraph(); ppr=p._p.get_or_add_pPr(); ppr.insert(0,OxmlElement('w:bidi'))
    p.alignment={'right':None,'center':WD_ALIGN_PARAGRAPH.CENTER,'left':WD_ALIGN_PARAGRAPH.RIGHT,'justify':WD_ALIGN_PARAGRAPH.JUSTIFY}[align]
    # note: in a bidi paragraph Word's 'left'(jc=left) means start=right; we use jc values explicitly below
    p.paragraph_format.space_after=Pt(space_after)
    if line: p.paragraph_format.line_spacing=line
    r=p.add_run(text); r.bold=bold
    rp=r._r.get_or_add_rPr(); rp.append(OxmlElement('w:rtl'))
    if bold: rp.append(OxmlElement('w:bCs'))
    if size:
        r.font.size=Pt(size); e=OxmlElement('w:szCs'); e.set(qn('w:val'),str(size*2)); rp.append(e)
    return p
def jc(p,val):
    ppr=p._p.get_or_add_pPr(); e=ppr.find(qn('w:jc'))
    if e is None: e=OxmlElement('w:jc'); ppr.append(e)
    e.set(qn('w:val'),val)
d.paragraphs[0]._p.getparent().remove(d.paragraphs[0]._p) if d.paragraphs else None
p=P('{%p if header_line %}'); p=P('{{ header_line }}',bold=True,size=13); jc(p,'center'); P('{%p endif %}')
# date / number block (end side = visual left in RTL)
for lbl in ('date','number','attachment'):
    P('{%%p if %s %%}'%lbl)
    p=P({'date':'تاریخ: ','number':'شماره: ','attachment':'پیوست: '}[lbl]+'{{ %s }}'%lbl,size=11,space_after=0); jc(p,'right')
    P('{%p endif %}')
P('',space_after=12)
P('{%p for line in addressee_lines %}'); P('{{ line }}',bold=True,space_after=2); P('{%p endfor %}')
P('{%p if subject %}'); P('موضوع: {{ subject }}',bold=True); P('{%p endif %}')
P('{{ salutation }}',space_after=4)
P('{%p for para in body_paragraphs %}'); p=P('{{ para }}',line=1.3); jc(p,'both'); P('{%p endfor %}')
P('',space_after=18)
p=P('{{ closing }}'); jc(p,'right')
# signature image placeholder: docxtpl InlineImage variable `signature_image` (None => nothing)
p=P('{%p if signature_image %}'); p=P('{{ signature_image }}'); jc(p,'right'); P('{%p endif %}')
p=P('{{ signer_name }}',bold=True); jc(p,'right')
P('{%p if signer_title %}'); p=P('{{ signer_title }}',size=11); jc(p,'right'); P('{%p endif %}')
d.save(sys.argv[1])
