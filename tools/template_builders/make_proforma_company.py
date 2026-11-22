import copy, sys
from docxlib import *
import lxml.etree as ET
d=Doc('pfc_src.docx'); b=d.body
tbl=b.find(q('tbl')); rows=tbl.findall(q('tr'))
def cells(tr): return tr.findall(q('tc'))
def paras(tc): return tc.findall(q('p'))
NSR='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
# --- seller / buyer rows
for i,who in ((0,'seller'),(1,'buyer')):
    c0,c1,_=cells(rows[i])
    pn,pa=paras(c1)[:2]
    set_text(pn,'نام: {{ %s.name }}'%who); set_text(pa,'نشانی: {{ %s.address }}{%% if %s.postal_code %%} - کدپستی: {{ %s.postal_code }}{%% endif %%}'%(who,who,who))
    pid=copy.deepcopy(pn); set_text(pid,'{%% if %s.national_id %%}شناسه ملی: {{ %s.national_id }}{%% endif %%}{%% if %s.economic_code %%}   کد اقتصادی: {{ %s.economic_code }}{%% endif %%}{%% if %s.registration_no %%}   شماره ثبت: {{ %s.registration_no }}{%% endif %%}'%((who,)*6)); pa.addnext(pid)
    pt,pf=paras(c0)[:2]
    set_text(pt,'تلفن: {{ %s.phone }}'%who); set_text(pf,'فاکس: {{ %s.fax }}'%who)
# --- item rows: keep row 3 as the loop row, drop row 4
r3,r4=rows[3],rows[4]
c=cells(r3)  # total, unit price, unit, qty, desc, #
vals=['{{ it.total }}','{{ it.unit_price }}','{{ it.unit }}','{{ it.qty }}','{{ it.description }}','{{ it.idx }}']
for tc,v in zip(c,vals):
    p=paras(tc)[0]; set_text(p,v)
    for extra in paras(tc)[1:]: tc.remove(extra)
r3.addprevious(tag_paragraph(paras(c[4])[0],'PLACEHOLDER'))  # temp, replaced below
r3.getprevious().getparent().remove(r3.getprevious())
def tag_row(like,text):
    tr=copy.deepcopy(like)
    tcs=cells(tr)
    for tc in tcs[1:]: tr.remove(tc)
    tc=tcs[0]
    for p in paras(tc)[1:]: tc.remove(p)
    set_text(paras(tc)[0],text); return tr
r3.addprevious(tag_row(r3,'{%tr for it in items %}')); r3.addnext(tag_row(r3,'{%tr endfor %}'))
tbl.remove(r4)
# --- totals rows: subtotal (only with VAT), VAT, payable
r5=rows[5]; c0,c1,c2=cells(r5)
sub=r5
set_text(paras(c2)[0],'جمع'); set_text(paras(c0)[0],'{{ totals.subtotal }}'); set_text(paras(c1)[0] if paras(c1) else ET.SubElement(c1,q('p')),'{{ totals.subtotal_words }}')
vat=copy.deepcopy(sub); vc0,vc1,vc2=cells(vat)
set_text(paras(vc2)[0],'ارزش افزوده'); set_text(paras(vc1)[0],'{{ totals.vat_percent }}% مالیات بر ارزش افزوده'); set_text(paras(vc0)[0],'{{ totals.vat }}')
pay=copy.deepcopy(sub); pc0,pc1,pc2=cells(pay)
set_text(paras(pc2)[0],'{{ totals.payable_label }}'); set_text(paras(pc1)[0],'{{ totals.payable_words }}'); set_text(paras(pc0)[0],'{{ totals.payable }}')
for tc in (pc0,pc1,pc2):
    for rpr in tc.iter(q('rPr')):
        if rpr.find(q('b')) is None: rpr.insert(0,ET.Element(q('b'))); rpr.insert(1,ET.Element(q('bCs')))
sub.addprevious(tag_row(sub,'{%tr if totals.vat_enabled %}'))
sub.addnext(vat); vat.addnext(tag_row(sub,'{%tr endif %}'))
vat.getnext().addnext(pay)
# --- clauses row
r6=rows[6]; n0,n1,n2=cells(r6)
ps=paras(n1); first=ps[0]
for p in ps[1:]: n1.remove(p)
set_text(first,'{{ loop.index }}- {{ cl }}')
first.addprevious(tag_paragraph(first,'{%p for cl in clauses %}')); first.addnext(tag_paragraph(first,'{%p endfor %}'))
lp=paras(n2)[0]; set_text(lp,'توضیحات')
r6.addprevious(tag_row(r6,'{%tr if clauses %}')); r6.addnext(tag_row(r6,'{%tr endif %}'))
# --- text boxes: date/number, title, closing; pictures conditional
for p in b.findall(q('p')):
    for tx in p.iter(q('txbxContent')):
        tps=tx.findall(q('p')); txt=''.join(runs_text(x) for x in tps)
        if 'تاریخ' in txt:
            set_text(tps[0],'تاریخ: {{ date }}')
            if len(tps)>1:
                np=tps[1]; set_text(np,'{% if number %}شماره: {{ number }}{% endif %}')
                np_ppr=np.find(q('pPr'))
        elif 'فاکتور' in txt or 'وضعیت' in txt:
            set_text(tps[0],'{{ title }}')
        elif 'بهرامی' in txt:
            set_text(tps[0],'{{ closing }}'); set_text(tps[-1],'{{ signer_name }}')
    for r in list(p.findall(q('r'))):
        blips=[e.get('{%s}embed'%NSR) for e in r.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip')]
        if not blips: continue
        flag={'rId11':'show_stamp','rId10':'show_signature'}.get(blips[0])
        if not flag: continue
        r.addprevious(text_run_like(r,'{%% if %s %%}'%flag)); r.addnext(text_run_like(r,'{% endif %}'))
d.save(sys.argv[1])
# report which images were wrapped
rels=d.files['word/_rels/document.xml.rels'].decode()
import re; print(re.findall(r'Id="(rId\d+)"[^>]*Target="(media/[^"]+)"',rels))
