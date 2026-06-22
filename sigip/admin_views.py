"""
Admin views for data import (CSV, Excel, JSON).
"""
import io
import tempfile
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.core.management import call_command


@staff_member_required
def import_data_view(request):
    context = {'title': 'Import de Dados'}

    if request.method == 'POST' and request.FILES.get('file'):
        uploaded = request.FILES['file']
        dry_run = 'dry_run' in request.POST
        skip_qc = 'skip_qc' in request.POST
        use_pip_excel = 'use_pip_excel' in request.POST

        # Save uploaded file to temp
        ext = Path(uploaded.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Capture command output
        out = io.StringIO()
        err = io.StringIO()

        try:
            if use_pip_excel and ext in ('.xlsx', '.xls'):
                # Use import_pip_excel command
                args = ['--file', tmp_path]
                if dry_run:
                    args.append('--dry-run')
                if skip_qc:
                    args.append('--skip-qc')
                call_command('import_pip_excel', *args, stdout=out, stderr=err)
            else:
                # Use generic import_data command
                args = ['--file', tmp_path]
                if dry_run:
                    args.append('--dry-run')
                call_command('import_data', *args, stdout=out, stderr=err)

            output = out.getvalue()
            err_output = err.getvalue()
            if err_output:
                output += '\n' + err_output

            context['result'] = output or 'Import termine avec succes.'
            context['error'] = False

        except Exception as e:
            context['result'] = f'Erreur: {e}\n\n{out.getvalue()}\n{err.getvalue()}'
            context['error'] = True

        finally:
            # Clean up temp file
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

    return render(request, 'admin/import_data.html', context)
