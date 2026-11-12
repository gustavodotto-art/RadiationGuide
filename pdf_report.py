"""Structured CT report. Synthetic example generation is in tests, never patient data."""
from html import escape
from pathlib import Path
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def fmt(value, unit=''):
    return 'não calculado / indisponível' if value is None else f'{value:.3f} {unit}'.strip()


def generate_pdf(data, output_path):
    # Embed ReportLab's bundled, licensed Vera fonts for consistent Portuguese
    # rendering on machines without Helvetica or configured system fonts.
    font_dir=Path(reportlab.__file__).parent/'fonts'
    for name,filename in [('RGVera','Vera.ttf'),('RGVeraBold','VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(font_dir/filename)))
    styles=getSampleStyleSheet()
    for name in ('Normal','BodyText','Title','Heading2'):
        styles[name].fontName='RGVeraBold' if name in ('Title','Heading2') else 'RGVera'
    styles.add(ParagraphStyle(name='SmallNote',parent=styles['BodyText'],fontSize=8,leading=11,spaceAfter=5))
    styles['Title'].textColor=colors.HexColor('#163553')
    def p(value,style='BodyText'): return Paragraph(escape(str(value)),styles[style])
    story=[p('Radiation Guide','Title'),p('Relatório técnico de TC para revisão de qualidade','Heading2'),
           p('Pseudônimo: '+data['patient_id']),p('Mês do exame: '+str(data.get('study_month') or 'indisponível')),
           p('Região: '+data['region']+' | Origem: '+data['_dose_source']),Spacer(1,5*mm)]
    rows=[[p('Grandeza'),p('Resultado')],
          [p('CTDIvol representativo'),p(fmt(data.get('ctdivol_mgy'),'mGy'))],
          [p('DLP total do estudo'),p(fmt(data.get('dlp_total_mgycm'),'mGy.cm'))],
          [p('SSDE'),p(fmt(data.get('ssde_mgy'),'mGy'))],
          [p('Diâmetro equivalente em água (Dw)'),p(fmt(data.get('dw_cm'),'cm'))],
          [p('Fantoma CTDI'),p(fmt(data.get('phantom_cm'),'cm'))]]
    t=Table(rows,colWidths=[87*mm,85*mm],hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef5')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#ccd6e0'))]))
    story += [t,Spacer(1,4*mm),p(data.get('ctdivol_summary',''),'SmallNote')]
    method=data.get('ssde_method') or data.get('ssde_reason')
    story += [p('SSDE: '+str(method),'SmallNote'),p('Triagem operacional interna','Heading2')]
    screen=data['screening']; ref=data['nrd']
    story += [p(screen['label']),p('Referência CTDIvol: '+fmt(ref.get('ctdivol'),'mGy'),'SmallNote'),
              p('Fonte: '+ref['source'],'SmallNote'),
              p('População: '+str(ref.get('population') or ref.get('reason')),'SmallNote'),
              p('Gatilhos de 80% e 100% servem apenas à triagem interna. Não representam limites individuais de dose nem veredito regulatório. A avaliação de DRL requer amostras representativas e medianas por protocolo (ICRP 135).','SmallNote')]
    if data.get('warnings'):
        story += [p('Limitações deste processamento','Heading2')]
        story += [p(w,'SmallNote') for w in data['warnings']]
    story += [Spacer(1,3*mm),p('O relatório contém pseudônimos e metadados técnicos. Não estima dose por órgão, risco individual nem dose efetiva. A pseudonimização não equivale a anonimização.','SmallNote')]
    doc=SimpleDocTemplate(output_path,pagesize=A4,rightMargin=19*mm,leftMargin=19*mm,topMargin=16*mm,bottomMargin=16*mm)
    def footer(c,doc):
        c.setFont('RGVera',7);c.setFillColor(colors.HexColor('#536779'))
        c.drawString(19*mm,10*mm,'Radiation Guide 2.0.0-rc1 | Controle de qualidade | Não substitui avaliação especializada')
        c.drawRightString(191*mm,10*mm,str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
