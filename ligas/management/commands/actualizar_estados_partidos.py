from django.core.management.base import BaseCommand
from ligas.models import Partido
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Detecta y actualiza automáticamente el estado de partidos que deberían estar en juego basándose en fecha/hora'

    def handle(self, *args, **options):
        ahora = timezone.now()
        fecha_hoy = ahora.date()
        hora_actual = ahora.time()
        
        # 1. Buscar partidos programados que ya deberían haber empezado
        partidos_a_empezar = Partido.objects.filter(
            estado='programado',
            fecha=fecha_hoy,
            hora__isnull=False,
            hora__lte=hora_actual
        )
        
        en_juego_count = 0
        for partido in partidos_a_empezar:
            # Verificar que no hayan pasado más de 2 horas (duración aproximada de un partido)
            fecha_hora_partido = datetime.combine(partido.fecha, partido.hora)
            if ahora - timezone.make_aware(fecha_hora_partido) < timedelta(hours=2):
                partido.estado = 'en_juego'
                if partido.goles_local is None:
                    partido.goles_local = 0
                if partido.goles_visitante is None:
                    partido.goles_visitante = 0
                partido.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'⚽ {partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre} -> EN JUEGO'
                    )
                )
                en_juego_count += 1
        
        # 2. Buscar partidos en juego que ya deberían haber finalizado (más de 2 horas)
        partidos_en_juego = Partido.objects.filter(
            estado='en_juego',
            fecha__isnull=False,
            hora__isnull=False
        )
        
        finalizados_count = 0
        for partido in partidos_en_juego:
            fecha_hora_partido = datetime.combine(partido.fecha, partido.hora)
            if ahora - timezone.make_aware(fecha_hora_partido) >= timedelta(hours=2):
                partido.estado = 'finalizado'
                partido.save()
                
                self.stdout.write(
                    self.style.WARNING(
                        f'✓ {partido.equipo_local.nombre} {partido.goles_local}-{partido.goles_visitante} '
                        f'{partido.equipo_visitante.nombre} -> FINALIZADO'
                    )
                )
                finalizados_count += 1
        
        # Resumen
        self.stdout.write('\n' + '='*60)
        if en_juego_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✓ {en_juego_count} partido(s) marcado(s) como EN JUEGO')
            )
        if finalizados_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✓ {finalizados_count} partido(s) marcado(s) como FINALIZADO')
            )
        if en_juego_count == 0 and finalizados_count == 0:
            self.stdout.write(
                self.style.WARNING('No hay partidos para actualizar en este momento')
            )
