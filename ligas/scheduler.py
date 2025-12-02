from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from .models import Liga, Partido
from .views import _scrape_liga
from django.utils import timezone
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def actualizar_estados_partidos():
    """Actualiza automáticamente el estado de partidos basándose en fecha/hora"""
    logger.info("Actualizando estados de partidos...")
    
    ahora = timezone.now()
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()
    
    # Buscar partidos programados que ya deberían haber empezado
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
            logger.info(f"Partido en juego: {partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre}")
            en_juego_count += 1
    
    # Buscar partidos en juego que ya deberían haber finalizado (más de 2 horas)
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
            logger.info(f"Partido finalizado: {partido.equipo_local.nombre} {partido.goles_local}-{partido.goles_visitante} {partido.equipo_visitante.nombre}")
            finalizados_count += 1
    
    logger.info(f"Estados actualizados: {en_juego_count} en juego, {finalizados_count} finalizados")

def actualizar_partidos_en_juego():
    """Actualiza solo los partidos que están en juego para obtener resultados en vivo"""
    logger.info("Actualizando partidos en juego...")
    
    # Obtener todas las ligas que tienen partidos en juego
    ligas_con_partidos_en_juego = Liga.objects.filter(
        partidos__estado='en_juego'
    ).distinct()
    
    partidos_actualizados = 0
    for liga in ligas_con_partidos_en_juego:
        try:
            logger.info(f"Actualizando partidos en juego de: {liga.nombre}")
            _scrape_liga(liga)
            partidos_actualizados += 1
        except Exception as e:
            logger.error(f"Error al actualizar partidos en juego de {liga.nombre}: {str(e)}")
    
    logger.info(f"Actualización de partidos en juego completada: {partidos_actualizados} ligas actualizadas")

def actualizar_ligas_automaticamente():
    """Actualiza todas las ligas activas"""
    logger.info("Iniciando actualización automática de ligas...")
    
    ligas_activas = Liga.objects.filter(activa=True)
    
    for liga in ligas_activas:
        try:
            logger.info(f"Actualizando liga: {liga.nombre}")
            partidos_actualizados = _scrape_liga(liga)
            liga.ultima_actualizacion = timezone.now()
            liga.save()
            logger.info(f"Liga {liga.nombre} actualizada: {partidos_actualizados} partidos procesados")
        except Exception as e:
            logger.error(f"Error al actualizar liga {liga.nombre}: {str(e)}")
    
    # Después de actualizar ligas, actualizar estados de partidos
    actualizar_estados_partidos()
    
    logger.info("Actualización automática completada")

def start_scheduler():
    """Inicia el scheduler para actualizar cada 15 minutos"""
    scheduler = BackgroundScheduler()
    
    # Agregar tarea que se ejecuta cada 15 minutos - actualización de ligas
    scheduler.add_job(
        actualizar_ligas_automaticamente,
        trigger=IntervalTrigger(minutes=15),
        id='actualizar_ligas',
        name='Actualizar ligas cada 15 minutos',
        replace_existing=True,
    )
    
    # Agregar tarea que se ejecuta cada 1 minuto - actualización de partidos en juego (resultados en vivo)
    scheduler.add_job(
        actualizar_partidos_en_juego,
        trigger=IntervalTrigger(minutes=1),
        id='actualizar_partidos_en_juego',
        name='Actualizar partidos en juego cada 1 minuto',
        replace_existing=True,
    )
    
    # Agregar tarea que se ejecuta cada 2 minutos - actualización de estados de partidos
    scheduler.add_job(
        actualizar_estados_partidos,
        trigger=IntervalTrigger(minutes=2),
        id='actualizar_estados',
        name='Actualizar estados de partidos cada 2 minutos',
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info("Scheduler iniciado: actualizaciones cada 15 minutos (ligas) y cada 2 minutos (estados)")
    
    return scheduler
