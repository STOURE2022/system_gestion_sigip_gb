"""
Migration: add StateFunction model and FK on Project.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sigip', '0002_project_rejection_note_project_workflow_status_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='StateFunction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=10, unique=True, verbose_name='Código')),
                ('label', models.CharField(max_length=255, verbose_name='Denominação')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Função do Estado',
                'verbose_name_plural': 'Funções do Estado',
                'ordering': ['order', 'code'],
            },
        ),
        migrations.AddField(
            model_name='project',
            name='state_function',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='projects',
                to='sigip.statefunction',
                verbose_name='Função do Estado',
            ),
        ),
    ]
