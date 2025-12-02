from django.apps import AppConfig


class LigasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ligas'
    
    def ready(self):
        """Inicia el scheduler cuando Django arranca"""
        from . import scheduler
        import sys
        import os
        
        # Solo iniciar scheduler en el proceso principal (no en reloader de desarrollo)
        if os.environ.get('RUN_MAIN') != 'true' and 'runserver' in sys.argv:
            return
        
        if not hasattr(self, '_scheduler_started'):
            scheduler.start_scheduler()
            self._scheduler_started = True
