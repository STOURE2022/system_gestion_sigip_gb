"""
SIGIP-GB PDF Generator
Génère la fiche officielle d'un projet PIP validé en PDF A4.
"""
from io import BytesIO
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable,
)
from django.utils import timezone

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
TEAL      = colors.HexColor('#1a7a6e')
TEAL_DARK = colors.HexColor('#0d5a50')
GOLD      = colors.HexColor('#c8961e')
DARK      = colors.HexColor('#1a1a2e')
INK2      = colors.HexColor('#555555')
MUTED     = colors.HexColor('#888888')
LIGHT_BG  = colors.HexColor('#f4f1ea')
GREEN_BG  = colors.HexColor('#d1fae5')
GREEN_FG  = colors.HexColor('#065f46')
GREEN_BD  = colors.HexColor('#a7f3d0')
WHITE     = colors.white


def _fmt(value):
    """Format Decimal/float as readable FCFA string."""
    try:
        v = float(value or 0)
        if v == 0:
            return '—'
        if v >= 1_000_000_000:
            return f'{v / 1_000_000_000:.2f} Md FCFA'
        if v >= 1_000_000:
            return f'{v / 1_000_000:.2f} M FCFA'
        if v >= 1_000:
            return f'{v / 1_000:.1f} K FCFA'
        return f'{v:,.0f} FCFA'
    except Exception:
        return str(value)


def generate_project_pdf(project) -> bytes:
    """
    Génère la fiche officielle d'un projet PIP validé.
    Retourne les octets du PDF A4.
    """
    from sigip.models import AnnualProgramming  # local import to avoid circulars

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f'SIGIP-GB — {project.code}',
        author='SIGIP-GB / DGP — República da Guiné-Bissau',
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 4 * cm  # usable width

    # -----------------------------------------------------------------------
    # Custom paragraph styles
    # -----------------------------------------------------------------------
    def st(name, **kw):
        base = kw.pop('parent', styles['Normal'])
        return ParagraphStyle(name, parent=base, **kw)

    hdr_title = st('HdrTitle', fontSize=20, textColor=TEAL,
                   fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
    hdr_sub   = st('HdrSub', fontSize=9, textColor=MUTED,
                   alignment=TA_CENTER, spaceAfter=2)
    sec_head  = st('SecHead', fontSize=8.5, textColor=WHITE,
                   fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=3,
                   leftIndent=0, backColor=TEAL,
                   borderPadding=(4, 6, 4, 6))
    lbl       = st('Lbl', fontSize=7.5, textColor=MUTED)
    val       = st('Val', fontSize=8.5, textColor=DARK, spaceAfter=4)
    desc_st   = st('Desc', fontSize=8, textColor=INK2, leading=12, spaceAfter=4)
    total_st  = st('Total', fontSize=11, textColor=TEAL,
                   fontName='Helvetica-Bold', alignment=TA_RIGHT)
    stamp_l   = st('StampL', fontSize=9, textColor=GREEN_FG,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)
    stamp_r   = st('StampR', fontSize=7.5, textColor=MUTED)
    note_st   = st('Note', fontSize=7, textColor=MUTED, alignment=TA_CENTER)

    story = []

    # -----------------------------------------------------------------------
    # HEADER
    # -----------------------------------------------------------------------
    story.append(Paragraph('SIGIP·GB', hdr_title))
    story.append(Paragraph(
        'Sistema de Gestão do Investimento Público — República da Guiné-Bissau', hdr_sub))
    story.append(Paragraph(
        'Direcção-Geral do Plano &nbsp;|&nbsp; Programa de Investimento Público 2026–2030', hdr_sub))
    story.append(HRFlowable(width='100%', thickness=2, color=TEAL, spaceAfter=3))
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD, spaceAfter=8))

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
        ('PADDING',     (0, 0), (-1, -1), 7),
    ]))
    story.append(banner)
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 1. IDENTIFICATION
    # -----------------------------------------------------------------------
    story.append(Paragraph('1. IDENTIFICAÇÃO DO PROJECTO', sec_head))
    story.append(Spacer(1, 4))

    def pair(label, value):
        return [Paragraph(label, lbl), Paragraph(str(value) if value else '—', val)]

    half = W / 2 - 0.1 * cm
    lbl_w = 3.5 * cm

    id_data = [
        [Paragraph('Código', lbl), Paragraph(project.code or '—', val),
         Paragraph('Estado de Validação', lbl), Paragraph('VALIDADO', st('V', fontSize=8.5, textColor=GREEN_FG, fontName='Helvetica-Bold'))],
        [Paragraph('Designação', lbl), Paragraph(project.title or '—', val),
         Paragraph('Estado de Execução', lbl), Paragraph(project.get_status_display() or '—', val)],
        [Paragraph('Ministério', lbl), Paragraph(str(project.ministry) if project.ministry else '—', val),
         Paragraph('Pilar PND', lbl), Paragraph(str(project.pillar) if project.pillar else '—', val)],
        [Paragraph('Sector', lbl), Paragraph(str(project.sector) if project.sector else '—', val),
         Paragraph('Prioridade Gov.', lbl), Paragraph(str(project.gov_priority) if project.gov_priority else '—', val)],
        [Paragraph('Financiador Principal', lbl), Paragraph(str(project.principal_financier) if project.principal_financier else '—', val),
         Paragraph('Região', lbl), Paragraph(str(project.region) if project.region else ('Nacional' if project.is_national else '—'), val)],
        [Paragraph('Data de Início', lbl), Paragraph(str(project.start_date) if project.start_date else '—', val),
         Paragraph('Data de Conclusão', lbl), Paragraph(str(project.end_date) if project.end_date else '—', val)],
    ]

    col_w = [2.8 * cm, 6.2 * cm, 3.0 * cm, 5.0 * cm]
    id_table = Table(id_data, colWidths=col_w)
    id_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (0, -1), LIGHT_BG),
        ('BACKGROUND',  (2, 0), (2, -1), LIGHT_BG),
        ('BACKGROUND',  (3, 0), (3, 0), GREEN_BG),
        ('GRID',        (0, 0), (-1, -1), 0.4, colors.HexColor('#d0ccc0')),
        ('PADDING',     (0, 0), (-1, -1), 5),
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(id_table)

    if project.description:
        story.append(Spacer(1, 5))
        story.append(Paragraph('Descrição', lbl))
        story.append(Paragraph(project.description[:600], desc_st))

    # -----------------------------------------------------------------------
    # 2. PROGRAMMATION
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 4))
    story.append(Paragraph('2. PROGRAMAÇÃO PLURIANUAL 2026–2030', sec_head))
    story.append(Spacer(1, 4))

    programmings = list(
        AnnualProgramming.objects.filter(project=project, version=1).order_by('fiscal_year')
    )

    hdr_row = ['Ano', 'Donativos', 'Empréstimos', 'Contr. Estado', 'Total do Ano']
    prog_rows = [hdr_row]

    total_don = Decimal('0')
    total_emp = Decimal('0')
    total_sta = Decimal('0')
    total_all = Decimal('0')

    for ap in programmings:
        yr_t = ap.donations + ap.loans + ap.state_contribution
        total_don += ap.donations
        total_emp += ap.loans
        total_sta += ap.state_contribution
        total_all += yr_t
        prog_rows.append([
            str(ap.fiscal_year),
            _fmt(ap.donations),
            _fmt(ap.loans),
            _fmt(ap.state_contribution),
            _fmt(yr_t),
        ])

    prog_rows.append(['TOTAL', _fmt(total_don), _fmt(total_emp), _fmt(total_sta), _fmt(total_all)])

    prog_col_w = [1.8 * cm, 4 * cm, 4 * cm, 4 * cm, 4.2 * cm]
    prog_table = Table(prog_rows, colWidths=prog_col_w)

    alt_rows = [('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fafaf8'))
                for i in range(2, len(prog_rows) - 1, 2)]
    prog_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND',  (0, 0), (-1, 0), TEAL),
        ('TEXTCOLOR',   (0, 0), (-1, 0), WHITE),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        # Total row
        ('BACKGROUND',  (0, -1), (-1, -1), LIGHT_BG),
        ('FONTNAME',    (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR',   (0, -1), (-1, -1), TEAL),
        # All cells
        ('FONTSIZE',    (0, 0), (-1, -1), 8),
        ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN',       (1, 1), (-1, -1), 'RIGHT'),
        ('GRID',        (0, 0), (-1, -1), 0.4, colors.HexColor('#d0ccc0')),
        ('PADDING',     (0, 0), (-1, -1), 5),
        *alt_rows,
    ]))
    story.append(prog_table)
    story.append(Spacer(1, 5))
    story.append(Paragraph(f'<b>CUSTO TOTAL DO PROJECTO: {_fmt(total_all)}</b>', total_st))

    # -----------------------------------------------------------------------
    # VALIDATION STAMP
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#d0ccc0')))
    story.append(Spacer(1, 6))

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
            f'<b>Sistema:</b> SIGIP-GB v1.0<br/>'
            f'<b>Referência:</b> PIP 2026–2030 / {project.code}',
            stamp_r
        ),
    ]]
    stamp_table = Table(stamp_data, colWidths=[W / 2, W / 2])
    stamp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GREEN_BG),
        ('BOX',        (0, 0), (-1, -1), 0.8, GREEN_BD),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING',    (0, 0), (-1, -1), 8),
    ]))
    story.append(stamp_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        'Documento gerado automaticamente pelo SIGIP-GB. '
        'Válido apenas com correspondência na base de dados do sistema.',
        note_st,
    ))

    doc.build(story)
    return buffer.getvalue()
