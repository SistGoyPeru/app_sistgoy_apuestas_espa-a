from collections import defaultdict
from ligas.models import Liga

def ligas_sidebar(request):
    """Context processor para mostrar el sidebar de ligas en todas las vistas"""
    ligas_por_continente = defaultdict(list)
    todas_ligas = Liga.objects.filter(activa=True).select_related().order_by('continente', 'nombre')
    
    for liga in todas_ligas:
        partidos_programados = liga.partidos.filter(estado='programado').count()
        ligas_por_continente[liga.continente].append({
            'id': liga.id,
            'nombre': liga.nombre,
            'pais': liga.pais,
            'partidos_programados': partidos_programados
        })
    
    # Ordenar continentes
    orden_continentes = ['europa', 'sudamerica', 'norteamerica', 'asia', 'africa', 'oceania']
    ligas_sidebar_data = {}
    for continente in orden_continentes:
        if continente in ligas_por_continente:
            ligas_sidebar_data[continente] = ligas_por_continente[continente]
    
    # Agregar continentes no previstos
    for continente, ligas in ligas_por_continente.items():
        if continente not in ligas_sidebar_data:
            ligas_sidebar_data[continente] = ligas
    
    return {
        'ligas_sidebar': ligas_sidebar_data
    }
