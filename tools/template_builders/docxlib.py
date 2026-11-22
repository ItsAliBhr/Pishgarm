"""Helpers to turn real Word documents into docxtpl (Jinja) templates by editing their XML."""
import zipfile, copy, re, shutil
import lxml.etree as ET
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s'%(W,t)
class Doc:
    def __init__(self,path):
        self.path=path; z=zipfile.ZipFile(path); self.files={n:z.read(n) for n in z.namelist()}
        self.tree=ET.fromstring(self.files['word/document.xml']); self.body=self.tree.find(q('body'))
    def save(self,out):
        self.files['word/document.xml']=ET.tostring(self.tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for n,d in self.files.items(): z.writestr(n,d)
def runs_text(p): return ''.join(t.text or '' for t in p.iter(q('t')))
def set_text(p,text):
    """Put text into the first run that has w:t; drop other text runs (keeps drawings)."""
    ts=list(p.iter(q('t')))
    if not ts:
        r=ET.SubElement(p,q('r')); t=ET.SubElement(r,q('t')); ts=[t]
    ts[0].text=text; ts[0].set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    keep=ts[0].getparent()
    for r in list(p.iter(q('r'))):
        if r is not keep and r.find(q('t')) is not None and r.find('.//'+q('drawing')) is None and r.find('.//{urn:schemas-microsoft-com:vml}shape') is None:
            r.getparent().remove(r)
    return p
def tag_paragraph(like,text):
    """A paragraph that holds only a docxtpl block tag like '{%p for x in xs %}', styled like `like`."""
    p=copy.deepcopy(like)
    for r in list(p.findall(q('r'))): p.remove(r)
    for el in list(p):
        if el.tag!=q('pPr'): p.remove(el)
    r=ET.SubElement(p,q('r')); t=ET.SubElement(r,q('t')); t.text=text
    return p
def text_run_like(run,text):
    r=copy.deepcopy(run)
    for el in list(r):
        if el.tag!=q('rPr'): r.remove(el)
    t=ET.SubElement(r,q('t')); t.text=text; t.set('{http://www.w3.org/XML/1998/namespace}space','preserve'); return r
