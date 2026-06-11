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
    # Implementar cache warming se necessário
    return {'status': 'ok'}
