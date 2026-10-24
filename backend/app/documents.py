"""Branded, paginated financial PDFs with embedded fonts and a real table."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

ASSETS=Path(__file__).parent/'assets'

def financial_document(title, number, details, charges):
    import reportlab
    fonts=Path(reportlab.__file__).parent/'fonts'
    if 'Cityhive' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Cityhive',str(fonts/'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('CityhiveBold',str(fonts/'VeraBd.ttf')))
    body=ParagraphStyle('body',fontName='Cityhive',fontSize=9,leading=14,textColor=colors.HexColor('#243047'))
    heading=ParagraphStyle('heading',parent=body,fontName='CityhiveBold',fontSize=21,leading=28)
    amount_style=ParagraphStyle('amount',parent=body,alignment=2)
    def p(value,style=body): return Paragraph(escape(str(value)).replace('\n','<br/>'),style)
    output=BytesIO()
    doc=SimpleDocTemplate(output,pagesize=(595,842),rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=52,
        title=f'{title} {number}',author="Cityhive Luxury PG's and Co-space",pageCompression=0)
    logo=ASSETS/'cityhive-mark.png'
    brand=p("CITYHIVE LUXURY PG'S AND CO-SPACE")
    story=[]
    if logo.exists():
        story.append(Table([[Image(str(logo),width=52,height=52,kind='proportional'),brand]],colWidths=[68,439],style=TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE')])))
    else: story.append(brand)
    story.extend([Spacer(1,22),p(title,heading),p(number),Spacer(1,20)])
    for label,value in details:
        if value is not None and str(value): story.append(p(f'{label}: {value}'))
    story.append(Spacer(1,22))
    rows=[[p('Description'),p('Amount (INR)',amount_style)]]+[[p(label),p(f'{amount:.2f}',amount_style)] for label,amount in charges]
    table=Table(rows,colWidths=[367,140],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9edf5')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),11),
        ('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#bec8d9')),
        ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dce2ec'))]))
    story.extend([table,Spacer(1,20),p('This document records configured accommodation charges and confirmed ledger entries. No tax or statutory registration claim is made.')])
    def footer(canvas,document):
        canvas.setFont('Cityhive',8);canvas.setFillColor(colors.HexColor('#687386'))
        canvas.drawString(44,29,'Cityhive | '+number);canvas.drawRightString(551,29,f'Page {document.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
