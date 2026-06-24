"""
SGPIP PDF Generator
Génère la fiche officielle d'un projet PIP validé en PDF A4.
"""
import math
from io import BytesIO
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable,
)
from django.utils import timezone

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
TEAL      = colors.HexColor('#0a4d4a')
TEAL_DARK = colors.HexColor('#073a38')
GOLD      = colors.HexColor('#c8961e')
GOLD_LIGHT = colors.HexColor('#f5eeda')
NAVY      = colors.HexColor('#0d1b2a')
INK2      = colors.HexColor('#333333')
MUTED     = colors.HexColor('#777777')
LIGHT_BG  = colors.HexColor('#f8f6f0')
GREEN_BG  = colors.HexColor('#e8f5ee')
GREEN_FG  = colors.HexColor('#065f46')
GREEN_BD  = colors.HexColor('#a7f3d0')
WHITE     = colors.white
LINE_CLR  = colors.HexColor('#d5d0c6')


def _draw_star(canvas, cx, cy, r, n=5, color=None):
    """Draw an n-pointed star at (cx, cy) with radius r."""
    if color:
        canvas.setFillColor(color)
        canvas.setStrokeColor(color)
    points = []
    for i in range(n * 2):
        angle = math.radians(90 + i * 180 / n)
        rad = r if i % 2 == 0 else r * 0.4
        points.append(cx + rad * math.cos(angle))
        points.append(cy + rad * math.sin(angle))
    p = canvas.beginPath()
    p.moveTo(points[0], points[1])
    for i in range(2, len(points), 2):
        p.lineTo(points[i], points[i + 1])
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)


def _draw_watermark(canvas, doc):
    """Draw a faint Guinea-Bissau coat of arms watermark in the center."""
    canvas.saveState()
    w, h = A4
    cx, cy = w / 2, h / 2

    # Large faint circle
    canvas.setFillColor(colors.HexColor('#00000008'))
    canvas.circle(cx, cy, 6 * cm, fill=1, stroke=0)

    # Inner circle
    canvas.setFillColor(colors.HexColor('#00000006'))
    canvas.circle(cx, cy, 4.5 * cm, fill=1, stroke=0)

    # Star (black star of Guinea-Bissau)
    _draw_star(canvas, cx, cy + 1.2 * cm, 1.8 * cm, 5, colors.HexColor('#00000010'))

    # Laurel branches (simplified as two arcs)
    canvas.setStrokeColor(colors.HexColor('#0000000A'))
    canvas.setLineWidth(3)
    # Left branch
    p = canvas.beginPath()
    p.arc(cx - 4 * cm, cy - 4 * cm, cx - 0.5 * cm, cy + 2 * cm, 30, 120)
    canvas.drawPath(p, fill=0, stroke=1)
    # Right branch
    p = canvas.beginPath()
    p.arc(cx + 0.5 * cm, cy - 4 * cm, cx + 4 * cm, cy + 2 * cm, 30, 120)
    canvas.drawPath(p, fill=0, stroke=1)

    # Text "REPÚBLICA DA GUINÉ-BISSAU" as very faint arc
    canvas.setFont('Helvetica-Bold', 7)
    canvas.setFillColor(colors.HexColor('#00000009'))
    canvas.drawCentredString(cx, cy - 3.8 * cm, 'REPÚBLICA DA GUINÉ-BISSAU')

    canvas.restoreState()


def _fmt(value):
    """Format Decimal/float as readable FCFA string with thousand separators."""
    try:
        v = float(value or 0)
        if v == 0:
            return '—'
        return f'{v:,.2f}'.replace(',', ' ').replace('.', ',') + ' FCFA'
    except Exception:
        return str(value)


def _fmt_short(value):
    """Format as short readable amount."""
    try:
        v = float(value or 0)
        if v == 0:
            return '—'
        if v >= 1_000_000_000:
            return f'{v / 1_000_000_000:.2f} Md FCFA'
        if v >= 1_000_000:
            return f'{v / 1_000_000:.2f} M FCFA'
        return f'{v:,.0f}'.replace(',', ' ') + ' FCFA'
    except Exception:
        return str(value)


def generate_project_pdf(project) -> bytes:
    """
    Génère la fiche officielle d'un projet PIP validé.
    Retourne les octets du PDF A4.
    """
    from sigip.models import AnnualProgramming

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f'SGPIP — {project.code}',
        author='SGPIP / DGP — República da Guiné-Bissau',
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 4 * cm

    # -----------------------------------------------------------------------
    # Custom paragraph styles
    # -----------------------------------------------------------------------
    def st(name, **kw):
        base = kw.pop('parent', styles['Normal'])
        return ParagraphStyle(name, parent=base, **kw)

    hdr_title = st('HdrTitle', fontSize=18, textColor=NAVY,
                   fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=14)
    hdr_sub   = st('HdrSub', fontSize=8.5, textColor=MUTED,
                   alignment=TA_CENTER, spaceAfter=2)
    sec_head  = st('SecHead', fontSize=9, textColor=WHITE,
                   fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=4,
                   leftIndent=0, backColor=TEAL,
                   borderPadding=(5, 8, 5, 8))
    lbl       = st('Lbl', fontSize=7.5, textColor=MUTED, fontName='Helvetica-Bold')
    val       = st('Val', fontSize=8.5, textColor=INK2, spaceAfter=3)
    val_bold  = st('ValBold', fontSize=9, textColor=NAVY, fontName='Helvetica-Bold', spaceAfter=3)
    desc_st   = st('Desc', fontSize=8.5, textColor=INK2, leading=13, spaceAfter=4)
    total_st  = st('Total', fontSize=12, textColor=TEAL,
                   fontName='Helvetica-Bold', alignment=TA_RIGHT)
    stamp_l   = st('StampL', fontSize=9, textColor=GREEN_FG,
                   fontName='Helvetica-Bold', alignment=TA_CENTER, leading=14)
    stamp_r   = st('StampR', fontSize=7.5, textColor=MUTED, leading=12)
    note_st   = st('Note', fontSize=7, textColor=MUTED, alignment=TA_CENTER)

    story = []

    # -----------------------------------------------------------------------
    # HEADER
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 4))
    story.append(Paragraph('SGPIP', hdr_title))
    story.append(Paragraph(
        'Sistema de Gestão do Programa de Investimento Público', hdr_sub))
    story.append(Paragraph(
        'República da Guiné-Bissau — Direcção-Geral do Plano', hdr_sub))
    story.append(Paragraph(
        'Programa de Investimento Público 2026–2030', hdr_sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width='100%', thickness=2.5, color=TEAL, spaceAfter=2))
    story.append(HRFlowable(width='100%', thickness=1.2, color=GOLD, spaceAfter=10))

    # Validated banner
    banner = Table(
        [['✓  FICHA DE PROJECTO VALIDADO']],
        colWidths=[W],
    )
    banner.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), GREEN_BG),
        ('TEXTCOLOR',   (0, 0), (-1, -1), GREEN_FG),
        ('FONTNAME',    (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 13),
        ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ('BOX',         (0, 0), (-1, -1), 1, GREEN_BD),
        ('PADDING',     (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(banner)
    story.append(Spacer(1, 12))

    # -----------------------------------------------------------------------
    # 1. IDENTIFICATION
    # -----------------------------------------------------------------------
    story.append(Paragraph('1. IDENTIFICAÇÃO DO PROJECTO', sec_head))
    story.append(Spacer(1, 6))

    id_data = [
        [Paragraph('Código', lbl), Paragraph(f'<b>{project.code or "—"}</b>', val_bold),
         Paragraph('Estado de Validação', lbl), Paragraph('<b>VALIDADO</b>', st('V', fontSize=9, textColor=GREEN_FG, fontName='Helvetica-Bold'))],
        [Paragraph('Nome do Projecto', lbl), Paragraph(project.title or '—', val),
         Paragraph('Estado de Execução', lbl), Paragraph(project.get_status_display() or '—', val)],
        [Paragraph('Ministério', lbl), Paragraph(str(project.ministry) if project.ministry else '—', val_bold),
         Paragraph('Sector', lbl), Paragraph(str(project.sector) if project.sector else '—', val)],
        [Paragraph('Financiador Principal', lbl), Paragraph(str(project.principal_financier) if project.principal_financier else '—', val_bold),
         Paragraph('Região', lbl), Paragraph(str(project.region) if project.region else ('Nacional' if project.is_national else '—'), val)],
        [Paragraph('Data de Início', lbl), Paragraph(str(project.start_date) if project.start_date else '—', val),
         Paragraph('Data de Conclusão', lbl), Paragraph(str(project.end_date) if project.end_date else '—', val)],
    ]

    col_w = [3.0 * cm, 6.0 * cm, 3.0 * cm, 5.0 * cm]
    id_table = Table(id_data, colWidths=col_w)
    id_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (0, -1), LIGHT_BG),
        ('BACKGROUND',  (2, 0), (2, -1), LIGHT_BG),
        ('BACKGROUND',  (3, 0), (3, 0), GREEN_BG),
        ('GRID',        (0, 0), (-1, -1), 0.4, LINE_CLR),
        ('PADDING',     (0, 0), (-1, -1), 6),
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(id_table)

    if project.description:
        story.append(Spacer(1, 8))
        story.append(Paragraph('<b>Descrição do Projecto</b>', lbl))
        story.append(Spacer(1, 3))
        story.append(Paragraph(project.description[:800], desc_st))

    # -----------------------------------------------------------------------
    # 2. PROGRAMMATION
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 6))
    story.append(Paragraph('2. PROGRAMAÇÃO PLURIANUAL 2026–2030', sec_head))
    story.append(Spacer(1, 6))

    programmings = list(
        AnnualProgramming.objects.filter(project=project, version=1).order_by('fiscal_year')
    )

    hdr_row = ['Ano', 'Donativos (FCFA)', 'Empréstimos (FCFA)',
               'Financ. Interno (FCFA)', 'Total do Ano']
    prog_rows = [hdr_row]

    total_don = Decimal('0')
    total_emp = Decimal('0')
    total_sta = Decimal('0')
    total_all = Decimal('0')

    # Ensure all years are shown even if no programming entry
    prog_by_year = {ap.fiscal_year: ap for ap in programmings}
    for yr in [2026, 2027, 2028, 2029, 2030]:
        ap = prog_by_year.get(yr)
        if ap:
            don = ap.donations
            emp = ap.loans
            sta = ap.state_contribution
        else:
            don = emp = sta = Decimal('0')
        yr_t = don + emp + sta
        total_don += don
        total_emp += emp
        total_sta += sta
        total_all += yr_t
        prog_rows.append([
            str(yr),
            _fmt(don),
            _fmt(emp),
            _fmt(sta),
            _fmt(yr_t),
        ])

    prog_rows.append(['TOTAL', _fmt(total_don), _fmt(total_emp), _fmt(total_sta), _fmt(total_all)])

    prog_col_w = [1.6 * cm, 4.1 * cm, 4.1 * cm, 4.1 * cm, 3.8 * cm]
    prog_table = Table(prog_rows, colWidths=prog_col_w)

    alt_rows = [('BACKGROUND', (0, i), (-1, i), colors.HexColor('#faf9f6'))
                for i in range(2, len(prog_rows) - 1, 2)]
    prog_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), TEAL),
        ('TEXTCOLOR',   (0, 0), (-1, 0), WHITE),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0), 8),
        # Total row
        ('BACKGROUND',  (0, -1), (-1, -1), GOLD_LIGHT),
        ('FONTNAME',    (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR',   (0, -1), (-1, -1), NAVY),
        # All cells
        ('FONTSIZE',    (0, 1), (-1, -1), 8),
        ('ALIGN',       (0, 0), (0, -1), 'CENTER'),
        ('ALIGN',       (1, 0), (-1, -1), 'RIGHT'),
        ('GRID',        (0, 0), (-1, -1), 0.4, LINE_CLR),
        ('PADDING',     (0, 0), (-1, -1), 5),
        *alt_rows,
    ]))
    story.append(prog_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f'<b>CUSTO TOTAL DO PROJECTO: {_fmt_short(total_all)}</b>', total_st))

    # -----------------------------------------------------------------------
    # VALIDATION STAMP
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width='100%', thickness=0.5, color=LINE_CLR))
    story.append(Spacer(1, 8))

    now_str = timezone.now().strftime('%d/%m/%Y à %H:%M')
    stamp_data = [[
        Paragraph(
            '<b>Projecto validado pela DGP</b><br/>'
            'Direcção-Geral do Plano<br/>'
            'República da Guiné-Bissau',
            stamp_l
        ),
        Paragraph(
            f'<b>Gerado em:</b> {now_str}<br/>'
            f'<b>Sistema:</b> SGPIP v1.0<br/>'
            f'<b>Referência:</b> PIP 2026–2030 / {project.code}',
            stamp_r
        ),
    ]]
    stamp_table = Table(stamp_data, colWidths=[W / 2, W / 2])
    stamp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GREEN_BG),
        ('BOX',        (0, 0), (-1, -1), 0.8, GREEN_BD),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING',    (0, 0), (-1, -1), 10),
    ]))
    story.append(stamp_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Documento gerado automaticamente pelo SGPIP. '
        'Válido apenas com correspondência na base de dados do sistema.',
        note_st,
    ))

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    return buffer.getvalue()
