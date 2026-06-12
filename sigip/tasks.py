"""
Celery tasks for SIGIP-GB.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='sigip.import_pip_data')
def import_pip_data_task(self, user_id=None, json_data=None, file_path=None):
    """
    Tarefa assíncrona para importar dados PIP.
    Pode receber JSON diretamente ou um caminho para ficheiro Excel/JSON.
    """
    import json, tempfile, os
    from pathlib import Path
    from django.core.management import call_command

    try:
        if json_data:
            # Write JSON data to a temp file and call the management command
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
                if isinstance(json_data, str):
                    tmp.write(json_data)
                else:
                    json.dump(json_data, tmp, ensure_ascii=False)
                tmp_path = tmp.name
            try:
                call_command('import_pip', file=tmp_path)
                result = {'imported': True, 'file': tmp_path}
            finally:
                os.unlink(tmp_path)
        elif file_path:
            call_command('import_pip', file=file_path)
            result = {'imported': True, 'file': file_path}
        else:
            return {'status': 'error', 'message': 'Nenhuma fonte de dados fornecida.'}

        logger.info(f'Import completed: {result}')
        return {'status': 'success', 'result': result}

    except Exception as e:
        logger.exception(f'Import task failed: {e}')
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(name='sigip.refresh_dashboard_cache')
def refresh_dashboard_cache():
    """Actualiza o cache do dashboard (opcional, para uso com Redis cache)."""
    logger.info('Refreshing dashboard cache...')
    return {'status': 'ok'}


@shared_task(name='sigip.send_workflow_notification', max_retries=2)
def send_workflow_notification_task(project_id, action, actor_id, rejection_note=''):
    """
    Envia notificações por e-mail após uma transição de workflow.

    action: 'submit' | 'validate' | 'reject' | 'unlock'

    Destinatários :
    - submit   → equipa DGP (ADMIN, DGP_ANALYST, VALIDATOR)
    - validate / reject / unlock → agentes do ministério do projecto + criador
    """
    from django.contrib.auth import get_user_model
    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    from sigip.models import Project
    from core.models import UserRole

    User = get_user_model()

    # ------------------------------------------------------------------
    # Load objects
    # ------------------------------------------------------------------
    try:
        project = Project.objects.select_related(
            'ministry', 'principal_financier', 'created_by'
        ).get(pk=project_id)
        actor = User.objects.get(pk=actor_id)
    except Exception as exc:
        logger.error(f'[notification] Object not found — {exc}')
        return {'status': 'error', 'message': str(exc)}

    # ------------------------------------------------------------------
    # Determine recipients
    # ------------------------------------------------------------------
    active_with_email = User.objects.filter(is_active=True).exclude(email='')

    if action == 'submit':
        recipients = list(
            active_with_email.filter(
                role__in=[UserRole.ADMIN, UserRole.DGP_ANALYST, UserRole.VALIDATOR]
            ).values_list('email', flat=True)
        )
    else:
        recipients = list(
            active_with_email.filter(
                role=UserRole.MINISTRY_AGENT,
                ministry=project.ministry,
            ).values_list('email', flat=True)
        )
        # Always include the project creator
        if project.created_by and project.created_by.email:
            if project.created_by.email not in recipients:
                recipients.append(project.created_by.email)

    if not recipients:
        logger.info(f'[notification] No recipients for {action} on {project.code}')
        return {'status': 'skipped', 'reason': 'no_recipients'}

    # ------------------------------------------------------------------
    # Build email content
    # ------------------------------------------------------------------
    subjects = {
        'submit':   f'[SIGIP-GB] Projecto submetido para validação — {project.code}',
        'validate': f'[SIGIP-GB] Projecto validado — {project.code}',
        'reject':   f'[SIGIP-GB] Projecto devolvido para correcções — {project.code}',
        'unlock':   f'[SIGIP-GB] Projecto reaberto — {project.code}',
    }
    subject = subjects.get(action, f'[SIGIP-GB] Actualização do projecto — {project.code}')

    context = {
        'project': project,
        'action': action,
        'actor': actor,
        'rejection_note': rejection_note,
        'app_url': 'https://systemgestionsigipgb-production.up.railway.app/app/',
    }

    html_body = render_to_string('emails/workflow_notification.html', context)

    # Plain text fallback
    action_labels = {
        'submit': 'Submetido para Validação',
        'validate': 'Validado',
        'reject': 'Devolvido para Correcções',
        'unlock': 'Reaberto para Edição',
    }
    plain = (
        f"{action_labels.get(action, action).upper()} — {project.code}\n\n"
        f"Projecto : {project.title}\n"
        f"Ministério: {project.ministry}\n"
        f"Realizado por: {actor.get_full_name() or actor.username}\n"
    )
    if rejection_note:
        plain += f"Observação: {rejection_note}\n"
    plain += f"\nAceder ao SIGIP-GB: {context['app_url']}"

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------
    sent = 0
    for email in recipients:
        try:
            send_mail(
                subject=subject,
                message=plain,
                from_email=None,          # Uses DEFAULT_FROM_EMAIL from settings
                recipient_list=[email],
                html_message=html_body,
                fail_silently=False,
            )
            sent += 1
        except Exception as exc:
            logger.error(f'[notification] Failed to send to {email}: {exc}')

    logger.info(
        f'[notification] {action} on {project.code}: '
        f'{sent}/{len(recipients)} emails sent'
    )
    return {'status': 'success', 'sent': sent, 'total': len(recipients)}
