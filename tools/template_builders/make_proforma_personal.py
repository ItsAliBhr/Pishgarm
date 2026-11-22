import copy, sys
from docxlib import *
import lxml.etree as ET
d=Doc('pp_src.docx'); b=d.body
tbl=b.find(q('tbl')); rows=tbl.findall(q('tr'))
cells=lambda tr: tr.findall(q('tc')); paras=lambda tc: tc.findall(q('p'))
def first_p(tc):
    ps=paras(tc)
    if not ps: ps=[ET.SubElement(tc,q('p'))]
    for p in ps[1:]: tc.remove(p)
    return ps[0]
def put(tc,text): set_text(first_p(tc),text)
for tr in rows[7:14]:
    for tc in cells(tr):
        pr=tc.find(q('tcPr'))
        if pr is not None:
            for vm in pr.findall(q('vMerge')): pr.remove(vm)
def tag_row(like,text):
    tr=copy.deepcopy(like); tcs=cells(tr)
    for tc in tcs[1:]: tr.remove(tc)
    tc=tcs[0]; pr=tc.find(q('tcPr'))
    put(tc,text); return tr
c=cells(rows[0]); put(c[0],'تاریخ : {{ date }}{% if number %}   شماره : {{ number }}{% endif %}'); put(c[1],'{{ title }}')
c=cells(rows[1]); put(c[0],'تلفن : {{ seller.phone }}'); put(c[1],'نام : {{ seller.name }}{% if seller.national_id %} - کد ملی : {{ seller.national_id }}{% endif %}')
c=cells(rows[2]); put(c[0],'{% if seller.fax %}فاکس : {{ seller.fax }}{% endif %}'); put(c[1],'آدرس : {{ seller.address }}')
c=cells(rows[3]); put(c[0],'تلفن : {{ buyer.phone }}'); put(c[1],'نام : {{ buyer.name }}')
c=cells(rows[4]); put(c[0],'فاکس : {{ buyer.fax }}'); put(c[1],'نشانی : {{ buyer.address }}{% if buyer.postal_code %} - کد پستی {{ buyer.postal_code }}{% endif %}')
# items
r=rows[6]; c=cells(r)
for tc,v in zip(c,['{{ it.total }}','{{ it.unit }}','{{ it.qty }}','{{ it.unit_price }}','{{ it.description }}','{{ it.idx }}']): put(tc,v)
r.addprevious(tag_row(r,'{%tr for it in items %}')); r.addnext(tag_row(r,'{%tr endfor %}'))
# clause rows (use the well-formed RTL paragraph of row 9 as the model for every clause list)
model=copy.deepcopy(paras(cells(rows[9])[1])[0])
for idx in (7,8,9):
    tc=cells(rows[idx])[1]
    for x in paras(tc): tc.remove(x)
    tc.append(copy.deepcopy(model))
tc=cells(rows[13])[1]
for x in paras(tc): tc.remove(x)
tc.append(copy.deepcopy(model))
for idx,(var,label) in zip((7,8,9),(('payment_clauses','شرایط پرداخت'),('delivery_clauses','شرایط حمل'),('other_clauses','سایر'))):
    r=rows[idx]; c=cells(r); put(c[0],'')
    ps=paras(c[1]); p=ps[0]
    for x in ps[1:]: c[1].remove(x)
    set_text(p,'{{ loop.index }}- {{ cl }}')
    p.addprevious(tag_paragraph(p,'{%%p for cl in %s %%}'%var)); p.addnext(tag_paragraph(p,'{%p endfor %}'))
    put(c[2],label)
    r.addprevious(tag_row(r,'{%%tr if %s %%}'%var)); r.addnext(tag_row(r,'{%tr endif %}'))
# totals
r10,r11,r12,r13=rows[10],rows[11],rows[12],rows[13]
c=cells(r10); put(c[0],'{{ totals.subtotal }}'); put(c[1],'{{ totals.subtotal_words }}'); put(c[2],'جمع')
c=cells(r11); put(c[0],'{{ totals.vat }}'); put(c[1],'{{ totals.vat_percent }}% ارزش افزوده'); put(c[2],'')
r10.addprevious(tag_row(r10,'{%tr if totals.vat_enabled %}')); r11.addnext(tag_row(r10,'{%tr endif %}'))
c=cells(r12); put(c[0],'{{ totals.payable }}'); put(c[1],'{{ totals.payable_label }} : {{ totals.payable_words }}'); put(c[2],'')
c=cells(r13); p=first_p(c[1]); 
src=paras(cells(rows[9])[1])  # copy run formatting from clause paragraph
set_text(p,'{{ loop.index }}- {{ cl }}')
p.addprevious(tag_paragraph(p,'{%p for cl in note_clauses %}')); p.addnext(tag_paragraph(p,'{%p endfor %}'))
r13.addprevious(tag_row(r13,'{%tr if note_clauses %}')); r13.addnext(tag_row(r13,'{%tr endif %}'))
# signature picture conditional
NSR='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
for r in list(rows[14].iter(q('r'))):
    if r.find('.//'+q('drawing')) is not None:
        r.addprevious(text_run_like(r,'{% if show_signature %}')); r.addnext(text_run_like(r,'{% endif %}'))
d.save(sys.argv[1])
