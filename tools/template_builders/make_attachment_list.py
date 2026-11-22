import sys, docx
from docx.shared import Pt, Cm, Mm, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
d=docx.Document(); s=d.sections[0]
s.page_width=Mm(210); s.page_height=Mm(297); s.left_margin=s.right_margin=Cm(2.3); s.top_margin=Cm(2.5)
st=d.styles['Normal']; st.font.size=Pt(13); st.font.name='B Nazanin'
rf=st.element.get_or_add_rPr().find(qn('w:rFonts'))
for a in ('ascii','hAnsi','cs','eastAsia'): rf.set(qn('w:'+a),'B Nazanin')
def P(text,bold=False,size=13,color=None,center=False,after=6):
    p=d.add_paragraph(); p._p.get_or_add_pPr().insert(0,OxmlElement('w:bidi'))
    if center:
        jc=OxmlElement('w:jc'); jc.set(qn('w:val'),'center'); p._p.get_or_add_pPr().append(jc)
    p.paragraph_format.space_after=Pt(after); p.paragraph_format.line_spacing=1.4
    r=p.add_run(text); r.bold=bold; r.font.size=Pt(size)
    rp=r._r.get_or_add_rPr(); rp.append(OxmlElement('w:rtl'))
    e=OxmlElement('w:szCs'); e.set(qn('w:val'),str(size*2)); rp.append(e)
    if bold: rp.append(OxmlElement('w:bCs'))
    if color: r.font.color.rgb=RGBColor.from_string(color)
P('{{ title }}',bold=True,size=16,center=True,after=2)
P('{%p if subtitle %}'); P('{{ subtitle }}',size=13,center=True,after=18); P('{%p endif %}')
P('{%p for it in items %}')
P('{%p if it.buyer_supplied %}'); P('{{ it.idx }}. {{ it.description }}{% if it.qty %} ({{ it.qty }} {{ it.unit }}){% endif %}',bold=True,color='C00000'); 
P('{%p elif it.emphasis %}'); P('{{ it.idx }}. {{ it.description }}{% if it.qty %} ({{ it.qty }} {{ it.unit }}){% endif %}',bold=True)
P('{%p else %}'); P('{{ it.idx }}. {{ it.description }}{% if it.qty %} ({{ it.qty }} {{ it.unit }}){% endif %}')
P('{%p endif %}')
P('{%p endfor %}')
P('{%p if footer_note %}'); P('',after=24); P('{{ footer_note }}',bold=True,size=14,color='C00000',center=True); P('{%p endif %}')
d.save(sys.argv[1])
