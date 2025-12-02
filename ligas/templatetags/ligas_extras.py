from django import template
from ligas.models import Liga
from collections import defaultdict

register = template.Library()

@register.simple_tag
def get_ligas_por_continente():
    """Obtiene las ligas activas agrupadas por continente"""
    ligas = Liga.objects.filter(activa=True).order_by('continente', 'nombre')
    
    ligas_por_continente = defaultdict(list)
    
    for liga in ligas:
        # Contar partidos programados
        partidos_programados = liga.partidos.filter(estado='programado').count()
        liga.partidos_programados = partidos_programados
        
        ligas_por_continente[liga.continente].append(liga)
    
    # Ordenar continentes
    orden_continentes = ['europa', 'sudamerica', 'norteamerica', 'asia', 'africa', 'oceania']
    ligas_ordenadas = {}
    
    for continente in orden_continentes:
        if continente in ligas_por_continente:
            ligas_ordenadas[continente] = ligas_por_continente[continente]
    
    # Agregar continentes no previstos
    for continente, ligas in ligas_por_continente.items():
        if continente not in ligas_ordenadas:
            ligas_ordenadas[continente] = ligas
    
    return ligas_ordenadas
