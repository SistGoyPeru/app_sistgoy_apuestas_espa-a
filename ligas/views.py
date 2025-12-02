from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Sum, Case, When, IntegerField
from .models import Liga, Equipo, Partido
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from django.utils import timezone


def home(request):
    """Vista principal con todas las ligas agrupadas por continente"""
    from datetime import datetime, timedelta
    
    ligas = Liga.objects.filter(activa=True).order_by('continente', 'nombre')
    
    # Agrupar ligas por continente
    ligas_por_continente = {}
    for liga in ligas:
        continente = liga.get_continente_display()
        if continente not in ligas_por_continente:
            ligas_por_continente[continente] = []
        ligas_por_continente[continente].append(liga)
    
    # Calcular estadísticas para cada liga
    continentes_stats = {}
    total_equipos_general = 0
    total_partidos_general = 0
    total_finalizados_general = 0
    
    for continente, ligas_continente in ligas_por_continente.items():
        stats_continente = []
        
        for liga in ligas_continente:
            total_partidos = liga.partidos.count()
            finalizados = liga.partidos.filter(estado='finalizado').count()
            programados = liga.partidos.filter(estado='programado').count()
            equipos_count = liga.equipos.count()
            
            # Calcular top 5 equipos por puntos
            equipos = liga.equipos.all()
            equipos_stats = []
            
            for equipo in equipos:
                from django.db.models import F
                # Victorias
                victorias = Partido.objects.filter(
                    Q(equipo_local=equipo, goles_local__gt=F('goles_visitante')) |
                    Q(equipo_visitante=equipo, goles_visitante__gt=F('goles_local')),
                    liga=liga,
                    estado='finalizado'
                ).count()
                
                # Empates
                empates = Partido.objects.filter(
                    Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
                    goles_local=F('goles_visitante'),
                    liga=liga,
                    estado='finalizado'
                ).count()
                
                puntos = victorias * 3 + empates
                
                equipos_stats.append({
                    'nombre': equipo.nombre,
                    'puntos': puntos,
                })
            
            # Ordenar por puntos y tomar top 5
            equipos_stats.sort(key=lambda x: x['puntos'], reverse=True)
            top_5 = equipos_stats[:5]
            
            # Calcular precisión promedio basada solo en pronósticos 1X2 guardados (mucho más rápido)
            precision_promedio = 0
            partidos_con_precision = liga.partidos.filter(
                estado='finalizado',
                pronostico_1x2__isnull=False,
                pronostico_1x2_acertado__isnull=False
            ).count()
            
            if partidos_con_precision > 0:
                aciertos = liga.partidos.filter(
                    estado='finalizado',
                    pronostico_1x2__isnull=False,
                    pronostico_1x2_acertado=True
                ).count()
                precision_promedio = round((aciertos / partidos_con_precision) * 100, 1)
            
            # Calcular precisión del pronóstico 1X2
            partidos_con_pronostico_1x2 = liga.partidos.filter(
                estado='finalizado',
                pronostico_1x2__isnull=False,
                pronostico_1x2_acertado__isnull=False
            )
            
            total_pronosticos_1x2 = partidos_con_pronostico_1x2.count()
            aciertos_1x2 = partidos_con_pronostico_1x2.filter(pronostico_1x2_acertado=True).count()
            precision_1x2 = round((aciertos_1x2 / total_pronosticos_1x2) * 100, 1) if total_pronosticos_1x2 > 0 else 0
            
            # Usar la misma precisión 1X2 como aproximación para TOP 3 (más rápido)
            # En producción, esto debería calcularse periódicamente con una tarea programada
            precision_top3_promedio = precision_1x2
            total_partidos_top3 = total_pronosticos_1x2  # Usar el mismo contador
            
            # Sumar totales generales
            total_equipos_general += equipos_count
            total_partidos_general += total_partidos
            total_finalizados_general += finalizados
            
            stats_continente.append({
                'liga': liga,
                'total_partidos': total_partidos,
                'finalizados': finalizados,
                'programados': programados,
                'equipos': equipos_count,
                'top_equipos': top_5,
                'precision_promedio': precision_promedio,
                'partidos_con_precision': partidos_con_precision,
                'precision_1x2': precision_1x2,
                'aciertos_1x2': aciertos_1x2,
                'total_pronosticos_1x2': total_pronosticos_1x2,
                'precision_top3_promedio': precision_top3_promedio,
                'total_partidos_top3': total_partidos_top3,
            })
        
        # Ordenar ligas por precisión (de mayor a menor)
        stats_continente.sort(key=lambda x: x['precision_promedio'], reverse=True)
        continentes_stats[continente] = stats_continente
    
    # Fechas por defecto para el formulario de PDF
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Obtener partidos finalizados hoy agrupados por liga
    from django.db.models import Count
    finalizados_hoy = Partido.objects.filter(
        estado='finalizado',
        fecha=today
    ).values('liga__nombre').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Obtener partidos en vivo
    partidos_en_vivo = Partido.objects.filter(
        estado='en_juego'
    ).select_related('liga', 'equipo_local', 'equipo_visitante').order_by('liga__nombre', 'jornada')
    
    context = {
        'continentes_stats': continentes_stats,
        'total_equipos': total_equipos_general,
        'total_partidos': total_partidos_general,
        'total_finalizados': total_finalizados_general,
        'finalizados_hoy': finalizados_hoy,
        'partidos_en_vivo': partidos_en_vivo,
        'today': today.strftime('%Y-%m-%d'),
        'tomorrow': tomorrow.strftime('%Y-%m-%d'),
        'fecha_desde': today.strftime('%Y-%m-%d'),
        'fecha_hasta': tomorrow.strftime('%Y-%m-%d'),
    }
    return render(request, 'ligas/home.html', context)


def agregar_liga(request):
    """Vista para agregar/actualizar una liga"""
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        url = request.POST.get('url')
        continente = request.POST.get('continente', 'europa')
        pais = request.POST.get('pais', '')
        
        if nombre and url:
            try:
                # Extraer código de liga de la URL
                match = re.search(r'/competition/(co\d+)/', url)
                codigo_liga = match.group(1) if match else ''
                
                liga, created = Liga.objects.get_or_create(
                    url=url,
                    defaults={
                        'nombre': nombre,
                        'continente': continente,
                        'pais': pais,
                        'codigo_liga': codigo_liga,
                        'activa': True
                    }
                )
                
                if not created:
                    liga.nombre = nombre
                    liga.continente = continente
                    liga.pais = pais
                    liga.ultima_actualizacion = timezone.now()
                    liga.save()
                
                # Scraping automático
                partidos_creados = _scrape_liga(liga)
                
                if created:
                    messages.success(request, f'Liga "{nombre}" agregada! {partidos_creados} partidos cargados.')
                else:
                    messages.success(request, f'Liga "{nombre}" actualizada! {partidos_creados} partidos procesados.')
                
                return redirect('ligas:home')
                
            except requests.RequestException as e:
                messages.error(request, f'Error al conectar con la URL: {str(e)}')
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
        else:
            messages.error(request, 'Nombre y URL son requeridos.')
    
    return render(request, 'ligas/agregar_liga.html')


def editar_liga(request, liga_id):
    """Vista para editar los datos de una liga (URL, nombre, país, etc.)"""
    liga = get_object_or_404(Liga, id=liga_id)
    
    if request.method == 'POST':
        url_anterior = liga.url
        
        liga.nombre = request.POST.get('nombre', liga.nombre)
        liga.url = request.POST.get('url', liga.url)
        liga.continente = request.POST.get('continente', liga.continente)
        liga.pais = request.POST.get('pais', liga.pais)
        
        # Actualizar código de liga si cambió la URL
        match = re.search(r'/competition/(co\d+)/', liga.url)
        liga.codigo_liga = match.group(1) if match else liga.codigo_liga
        
        liga.save()
        
        # Si cambió la URL, actualizar automáticamente los datos
        if url_anterior != liga.url:
            try:
                partidos_actualizados = _scrape_liga(liga)
                messages.success(request, f'Liga "{liga.nombre}" actualizada y datos recargados! {partidos_actualizados} partidos procesados.')
            except Exception as e:
                messages.warning(request, f'Liga actualizada pero hubo un error al recargar datos: {str(e)}')
        else:
            messages.success(request, f'Liga "{liga.nombre}" actualizada correctamente.')
        
        return redirect('ligas:home')
    
    context = {
        'liga': liga,
        'continentes': [
            ('europa', 'Europa'),
            ('america', 'América'),
            ('asia', 'Asia'),
            ('africa', 'África'),
            ('oceania', 'Oceanía')
        ]
    }
    return render(request, 'ligas/editar_liga.html', context)


def actualizar_liga(request, liga_id):
    """Vista para actualizar los datos de una liga"""
    liga = get_object_or_404(Liga, id=liga_id)
    
    try:
        partidos_actualizados = _scrape_liga(liga)
        messages.success(request, f'Liga "{liga.nombre}" actualizada! {partidos_actualizados} partidos procesados.')
    except Exception as e:
        messages.error(request, f'Error al actualizar: {str(e)}')
    
    return redirect('ligas:home')


def lista_partidos(request, liga_id):
    """Vista para listar partidos de una liga - divididos en por jugar, en juego y jugados"""
    liga = get_object_or_404(Liga, id=liga_id)
    
    from datetime import date
    fecha_hoy = date.today()
    
    # Partidos por jugar (programados, desde hoy en adelante)
    partidos_por_jugar = liga.partidos.filter(
        estado='programado',
        fecha__gte=fecha_hoy
    ).select_related('equipo_local', 'equipo_visitante').order_by('fecha', 'jornada', 'hora')
    
    # Partidos en juego
    partidos_en_juego = liga.partidos.filter(
        estado='en_juego'
    ).select_related('equipo_local', 'equipo_visitante').order_by('jornada')
    
    # Partidos jugados (finalizados)
    partidos_jugados = liga.partidos.filter(
        estado='finalizado'
    ).select_related('equipo_local', 'equipo_visitante').order_by('-fecha', '-jornada')
    
    context = {
        'liga': liga,
        'partidos_por_jugar': partidos_por_jugar,
        'partidos_en_juego': partidos_en_juego,
        'partidos_jugados': partidos_jugados,
    }
    
    return render(request, 'ligas/lista_partidos.html', context)


def estadisticas(request, liga_id):
    """Vista con estadísticas completas y tabla de posiciones"""
    liga = get_object_or_404(Liga, id=liga_id)
    equipos = liga.equipos.all()
    
    estadisticas_equipos = []
    
    for equipo in equipos:
        partidos_jugados = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Victorias
        from django.db.models import F
        victorias = Partido.objects.filter(
            Q(equipo_local=equipo, goles_local__gt=F('goles_visitante')) |
            Q(equipo_visitante=equipo, goles_visitante__gt=F('goles_local')),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Empates
        empates = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            goles_local=F('goles_visitante'),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Derrotas
        derrotas = partidos_jugados - victorias - empates
        
        # Goles a favor y en contra
        partidos_local = Partido.objects.filter(equipo_local=equipo, liga=liga, estado='finalizado')
        partidos_visitante = Partido.objects.filter(equipo_visitante=equipo, liga=liga, estado='finalizado')
        
        goles_favor = sum([p.goles_local or 0 for p in partidos_local]) + sum([p.goles_visitante or 0 for p in partidos_visitante])
        goles_contra = sum([p.goles_visitante or 0 for p in partidos_local]) + sum([p.goles_local or 0 for p in partidos_visitante])
        
        puntos = victorias * 3 + empates
        diferencia_goles = goles_favor - goles_contra
        
        # Últimos 5 partidos (racha)
        ultimos_partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            liga=liga,
            estado='finalizado'
        ).order_by('-fecha', '-jornada')[:5]
        
        racha = []
        for p in ultimos_partidos:
            if p.equipo_local == equipo:
                if p.goles_local > p.goles_visitante:
                    racha.append('V')
                elif p.goles_local < p.goles_visitante:
                    racha.append('D')
                else:
                    racha.append('E')
            else:
                if p.goles_visitante > p.goles_local:
                    racha.append('V')
                elif p.goles_visitante < p.goles_local:
                    racha.append('D')
                else:
                    racha.append('E')
        
        estadisticas_equipos.append({
            'equipo': equipo,
            'partidos_jugados': partidos_jugados,
            'victorias': victorias,
            'empates': empates,
            'derrotas': derrotas,
            'goles_favor': goles_favor,
            'goles_contra': goles_contra,
            'diferencia_goles': diferencia_goles,
            'puntos': puntos,
            'racha': racha,
        })
    
    # Ordenar por puntos, diferencia de goles y goles a favor
    estadisticas_equipos.sort(key=lambda x: (x['puntos'], x['diferencia_goles'], x['goles_favor']), reverse=True)
    
    # Estadísticas generales de la liga
    mejor_ataque = max(estadisticas_equipos, key=lambda x: x['goles_favor']) if estadisticas_equipos else None
    mejor_defensa = min(estadisticas_equipos, key=lambda x: x['goles_contra']) if estadisticas_equipos else None
    mas_puntos = estadisticas_equipos[0] if estadisticas_equipos else None
    
    total_goles = sum([e['goles_favor'] for e in estadisticas_equipos])
    total_partidos = liga.partidos.filter(estado='finalizado').count()
    promedio_goles = round(total_goles / total_partidos, 2) if total_partidos > 0 else 0
    
    context = {
        'liga': liga,
        'estadisticas': estadisticas_equipos,
    }
    
    return render(request, 'ligas/estadisticas.html', context)


def estadisticas_completas(request, liga_id):
    """Vista con estadísticas completas y detalladas de la liga"""
    liga = get_object_or_404(Liga, id=liga_id)
    equipos = liga.equipos.all()
    
    estadisticas_equipos = []
    
    for equipo in equipos:
        partidos_jugados = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Victorias
        from django.db.models import F
        victorias = Partido.objects.filter(
            Q(equipo_local=equipo, goles_local__gt=F('goles_visitante')) |
            Q(equipo_visitante=equipo, goles_visitante__gt=F('goles_local')),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Empates
        empates = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            goles_local=F('goles_visitante'),
            liga=liga,
            estado='finalizado'
        ).count()
        
        # Derrotas
        derrotas = partidos_jugados - victorias - empates
        
        # Goles a favor y en contra
        partidos_local = Partido.objects.filter(equipo_local=equipo, liga=liga, estado='finalizado')
        partidos_visitante = Partido.objects.filter(equipo_visitante=equipo, liga=liga, estado='finalizado')
        
        goles_favor = sum([p.goles_local or 0 for p in partidos_local]) + sum([p.goles_visitante or 0 for p in partidos_visitante])
        goles_contra = sum([p.goles_visitante or 0 for p in partidos_local]) + sum([p.goles_local or 0 for p in partidos_visitante])
        
        puntos = victorias * 3 + empates
        diferencia_goles = goles_favor - goles_contra
        
        # Últimos 5 partidos (racha)
        ultimos_partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            liga=liga,
            estado='finalizado'
        ).order_by('-fecha', '-jornada')[:5]
        
        racha = []
        for p in ultimos_partidos:
            if p.equipo_local == equipo:
                if p.goles_local > p.goles_visitante:
                    racha.append('V')
                elif p.goles_local < p.goles_visitante:
                    racha.append('D')
                else:
                    racha.append('E')
            else:
                if p.goles_visitante > p.goles_local:
                    racha.append('V')
                elif p.goles_visitante < p.goles_local:
                    racha.append('D')
                else:
                    racha.append('E')
        
        estadisticas_equipos.append({
            'equipo': equipo,
            'partidos_jugados': partidos_jugados,
            'victorias': victorias,
            'empates': empates,
            'derrotas': derrotas,
            'goles_favor': goles_favor,
            'goles_contra': goles_contra,
            'diferencia_goles': diferencia_goles,
            'puntos': puntos,
            'racha': racha,
        })
    
    # Ordenar por puntos, diferencia de goles y goles a favor
    estadisticas_equipos.sort(key=lambda x: (x['puntos'], x['diferencia_goles'], x['goles_favor']), reverse=True)
    
    # Estadísticas generales de la liga
    mejor_ataque = max(estadisticas_equipos, key=lambda x: x['goles_favor']) if estadisticas_equipos else None
    mejor_defensa = min(estadisticas_equipos, key=lambda x: x['goles_contra']) if estadisticas_equipos else None
    mas_puntos = estadisticas_equipos[0] if estadisticas_equipos else None
    
    total_goles = sum([e['goles_favor'] for e in estadisticas_equipos])
    total_partidos = liga.partidos.filter(estado='finalizado').count()
    total_partidos_programados = liga.partidos.filter(estado='programado').count()
    total_partidos_liga = total_partidos + total_partidos_programados
    porcentaje_jugados = round((total_partidos / total_partidos_liga * 100), 1) if total_partidos_liga > 0 else 0
    promedio_goles = round(total_goles / total_partidos, 2) if total_partidos > 0 else 0
    
    # Estadísticas Over/Under (1.5, 2.5, 3.5, 4.5 goles)
    partidos_finalizados = liga.partidos.filter(
        estado='finalizado',
        goles_local__isnull=False,
        goles_visitante__isnull=False
    )
    
    over_15 = 0
    over_25 = 0
    over_35 = 0
    over_45 = 0
    
    for partido in partidos_finalizados:
        total_goles_partido = (partido.goles_local or 0) + (partido.goles_visitante or 0)
        if total_goles_partido > 1.5:
            over_15 += 1
        if total_goles_partido > 2.5:
            over_25 += 1
        if total_goles_partido > 3.5:
            over_35 += 1
        if total_goles_partido > 4.5:
            over_45 += 1
    
    under_15 = total_partidos - over_15
    under_25 = total_partidos - over_25
    under_35 = total_partidos - over_35
    under_45 = total_partidos - over_45
    
    porcentaje_over_15 = round((over_15 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_over_25 = round((over_25 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_over_35 = round((over_35 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_over_45 = round((over_45 / total_partidos * 100), 1) if total_partidos > 0 else 0
    
    porcentaje_under_15 = round((under_15 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_under_25 = round((under_25 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_under_35 = round((under_35 / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_under_45 = round((under_45 / total_partidos * 100), 1) if total_partidos > 0 else 0
    
    # Estadística Ambos Marcan (BTTS - Both Teams To Score)
    ambos_marcan = 0
    ambos_no_marcan = 0
    
    for partido in partidos_finalizados:
        goles_local = partido.goles_local or 0
        goles_visitante = partido.goles_visitante or 0
        if goles_local > 0 and goles_visitante > 0:
            ambos_marcan += 1
        else:
            ambos_no_marcan += 1
    
    porcentaje_ambos_marcan = round((ambos_marcan / total_partidos * 100), 1) if total_partidos > 0 else 0
    porcentaje_ambos_no_marcan = round((ambos_no_marcan / total_partidos * 100), 1) if total_partidos > 0 else 0
    
    # Histograma de resultados (distribución de goles totales por partido)
    histograma_resultados = {}
    for partido in partidos_finalizados:
        total_goles_partido = (partido.goles_local or 0) + (partido.goles_visitante or 0)
        if total_goles_partido in histograma_resultados:
            histograma_resultados[total_goles_partido] += 1
        else:
            histograma_resultados[total_goles_partido] = 1
    
    # Ordenar por número de goles y preparar datos para el gráfico
    histograma_labels = sorted(histograma_resultados.keys())
    histograma_valores = [histograma_resultados[goles] for goles in histograma_labels]
    
    # Histograma de resultados exactos (0-0, 1-0, 0-1, 1-1, etc.)
    resultados_exactos = {}
    
    for partido in partidos_finalizados:
        goles_local = partido.goles_local or 0
        goles_visitante = partido.goles_visitante or 0
        resultado = f"{goles_local}-{goles_visitante}"
        
        if resultado in resultados_exactos:
            resultados_exactos[resultado] += 1
        else:
            resultados_exactos[resultado] = 1
    
    # Ordenar por frecuencia (más comunes primero) y tomar los top 15
    resultados_ordenados = sorted(resultados_exactos.items(), key=lambda x: x[1], reverse=True)[:15]
    resultados_exactos_labels = [r[0] for r in resultados_ordenados]
    resultados_exactos_valores = [r[1] for r in resultados_ordenados]
    
    # Calcular promedio de precisión (muestra de últimos 15 partidos)
    # Usando servicios optimizados con caché automático
    precision_promedio = 0
    partidos_con_precision = 0
    muestra_partidos = partidos_finalizados.order_by('-fecha', '-jornada')[:15]
    
    for partido in muestra_partidos:
        if partido.goles_local is not None and partido.goles_visitante is not None:
            try:
                # Calcular estadísticas
                stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                
                # Calcular pronóstico
                pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                
                # Verificar precisión
                precision_analisis = _verificar_precision_pronostico(partido, pronostico)
                precision_promedio += precision_analisis['porcentaje_aciertos']
                partidos_con_precision += 1
            except Exception:
                continue
    
    if partidos_con_precision > 0:
        precision_promedio = round(precision_promedio / partidos_con_precision, 1)
    
    # Calcular precisión del pronóstico 1X2
    partidos_con_pronostico_1x2 = liga.partidos.filter(
        estado='finalizado',
        pronostico_1x2__isnull=False,
        pronostico_1x2_acertado__isnull=False
    )
    
    total_pronosticos_1x2 = partidos_con_pronostico_1x2.count()
    aciertos_1x2 = partidos_con_pronostico_1x2.filter(pronostico_1x2_acertado=True).count()
    precision_1x2 = round((aciertos_1x2 / total_pronosticos_1x2) * 100, 1) if total_pronosticos_1x2 > 0 else 0
    
    # Calcular precisión del TOP 3 (últimos 30 partidos finalizados)
    # Usando servicios optimizados con caché automático
    precision_top3_promedio = 0
    total_partidos_top3 = 0
    
    ultimos_finalizados = liga.partidos.filter(estado='finalizado').order_by('-fecha', '-jornada')[:30]
    
    for partido in ultimos_finalizados:
        if partido.goles_local is not None and partido.goles_visitante is not None:
            try:
                # Calcular estadísticas
                stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                
                # Calcular pronóstico
                pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                
                # Verificar precisión
                precision_analisis = _verificar_precision_pronostico(partido, pronostico)
                
                if precision_analisis.get('precision_top3') is not None:
                    precision_top3_promedio += precision_analisis['precision_top3']
                    total_partidos_top3 += 1
            except Exception:
                continue
    
    if total_partidos_top3 > 0:
        precision_top3_promedio = round(precision_top3_promedio / total_partidos_top3, 1)
    
    context = {
        'liga': liga,
        'estadisticas': estadisticas_equipos,
        'mejor_ataque': mejor_ataque,
        'mejor_defensa': mejor_defensa,
        'mas_puntos': mas_puntos,
        'total_goles': total_goles,
        'total_partidos': total_partidos,
        'total_partidos_liga': total_partidos_liga,
        'porcentaje_jugados': porcentaje_jugados,
        'promedio_goles': promedio_goles,
        'precision_promedio': precision_promedio,
        'partidos_con_precision': partidos_con_precision,
        'precision_1x2': precision_1x2,
        'aciertos_1x2': aciertos_1x2,
        'total_pronosticos_1x2': total_pronosticos_1x2,
        'precision_top3_promedio': precision_top3_promedio,
        'total_partidos_top3': total_partidos_top3,
        'over_15': over_15,
        'over_25': over_25,
        'over_35': over_35,
        'over_45': over_45,
        'under_15': under_15,
        'under_25': under_25,
        'under_35': under_35,
        'under_45': under_45,
        'porcentaje_over_15': porcentaje_over_15,
        'porcentaje_over_25': porcentaje_over_25,
        'porcentaje_over_35': porcentaje_over_35,
        'porcentaje_over_45': porcentaje_over_45,
        'porcentaje_under_15': porcentaje_under_15,
        'porcentaje_under_25': porcentaje_under_25,
        'porcentaje_under_35': porcentaje_under_35,
        'porcentaje_under_45': porcentaje_under_45,
        'ambos_marcan': ambos_marcan,
        'ambos_no_marcan': ambos_no_marcan,
        'porcentaje_ambos_marcan': porcentaje_ambos_marcan,
        'porcentaje_ambos_no_marcan': porcentaje_ambos_no_marcan,
        'histograma_labels': histograma_labels,
        'histograma_valores': histograma_valores,
        'resultados_exactos_labels': resultados_exactos_labels,
        'resultados_exactos_valores': resultados_exactos_valores,
    }
    
    return render(request, 'ligas/estadisticas_completas.html', context)


def _scrape_liga(liga):
    """Función interna para hacer scraping de una liga (basada en extraer_data.py)"""
    response = requests.get(liga.url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    gameplan = soup.find('div', class_='module-gameplan')
    if not gameplan:
        return 0
    
    wrapper = gameplan.find('div', recursive=False)
    if not wrapper:
        return 0
    
    current_round = None
    equipos_cache = {}
    partidos_count = 0
    
    for child in wrapper.find_all(recursive=False):
        classes = child.get('class', [])
        
        if 'round-head' in classes:
            round_text = child.get_text(strip=True)
            round_match = re.search(r'(\d+)', round_text)
            current_round = int(round_match.group(1)) if round_match else None
        
        elif 'match' in classes and current_round:
                # Extraer fecha y hora
                datetime_str = child.get('data-datetime')
                fecha_val = None
                hora_val = None
                
                if datetime_str:
                    try:
                        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                        fecha_val = dt.date()
                        hora_val = dt.time()
                    except:
                        pass
                
                # Extraer equipos
                team_home_elem = child.find('div', class_='team-name-home')
                team_away_elem = child.find('div', class_='team-name-away')
                
                if not team_home_elem or not team_away_elem:
                    continue
                
                nombre_local = team_home_elem.get_text(strip=True)
                nombre_visitante = team_away_elem.get_text(strip=True)
                
                # Obtener o crear equipos
                if nombre_local not in equipos_cache:
                    equipo_local, _ = Equipo.objects.get_or_create(
                        nombre=nombre_local,
                        liga=liga
                    )
                    equipos_cache[nombre_local] = equipo_local
                
                if nombre_visitante not in equipos_cache:
                    equipo_visitante, _ = Equipo.objects.get_or_create(
                        nombre=nombre_visitante,
                        liga=liga
                    )
                    equipos_cache[nombre_visitante] = equipo_visitante
                
                # Extraer resultado
                result_elem = child.find('div', class_='match-result')
                goles_local = None
                goles_visitante = None
                estado = 'programado'
                
                # Detectar si el partido está en juego (buscar indicador de "live" o "en vivo")
                is_live = False
                live_indicator = child.find(class_=lambda x: x and ('live' in x.lower() or 'playing' in x.lower()))
                if live_indicator:
                    is_live = True
                
                # También verificar si tiene atributo data-status
                data_status = child.get('data-status', '').lower()
                if 'live' in data_status or 'playing' in data_status or 'in_progress' in data_status:
                    is_live = True
                
                if result_elem:
                    result_text = result_elem.get_text(strip=True)
                    if ':' in result_text and result_text != '-:-':
                        try:
                            parts = result_text.split(':')
                            if len(parts) == 2:
                                goles_local = int(parts[0].strip())
                                goles_visitante = int(parts[1].strip())
                                
                                # Si hay resultado pero está marcado como live, está en juego
                                if is_live:
                                    estado = 'en_juego'
                                else:
                                    # Verificar si el partido es de hoy y en horario reciente
                                    from datetime import datetime, timedelta
                                    if fecha_val and hora_val:
                                        fecha_hora_partido = datetime.combine(fecha_val, hora_val)
                                        ahora = datetime.now()
                                        # Si el partido empezó hace menos de 3 horas y tiene resultado, probablemente está en juego
                                        if ahora - fecha_hora_partido < timedelta(hours=3) and ahora > fecha_hora_partido:
                                            estado = 'en_juego'
                                        else:
                                            estado = 'finalizado'
                                    else:
                                        estado = 'finalizado'
                        except (ValueError, IndexError):
                            pass
                    elif is_live:
                        # Si está marcado como live pero no tiene resultado todavía
                        estado = 'en_juego'
                        goles_local = 0
                        goles_visitante = 0
                
                # Crear o actualizar partido
                Partido.objects.update_or_create(
                    liga=liga,
                    jornada=current_round,
                    equipo_local=equipos_cache[nombre_local],
                    equipo_visitante=equipos_cache[nombre_visitante],
                    defaults={
                        'goles_local': goles_local,
                        'goles_visitante': goles_visitante,
                        'estado': estado,
                        'fecha': fecha_val,
                        'hora': hora_val,
                    }
                )
                partidos_count += 1
    
    return partidos_count


def comparacion_equipos(request, partido_id):
    """Vista para comparar las estadísticas de dos equipos de un partido"""
    partido = get_object_or_404(Partido, id=partido_id)
    equipo_local = partido.equipo_local
    equipo_visitante = partido.equipo_visitante
    liga = partido.liga
    
    # Calcular estadísticas
    stats_local = _calcular_estadisticas_equipo(equipo_local, liga)
    stats_visitante = _calcular_estadisticas_equipo(equipo_visitante, liga)
    
    # Obtener últimos partidos (ya vienen en formato de diccionario)
    ultimos_local = _obtener_ultimos_partidos(equipo_local, liga, 5)
    ultimos_visitante = _obtener_ultimos_partidos(equipo_visitante, liga, 5)
    
    # Calcular pronóstico
    pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
    
    # Guardar pronóstico 1X2 si aún no se ha guardado
    if not partido.pronostico_1x2 and partido.estado == 'programado':
        partido.pronostico_1x2 = pronostico['recomendacion']
        partido.save()
    
    # Si el partido está finalizado, verificar precisión del pronóstico
    precision_analisis = None
    if partido.estado == 'finalizado':
        precision_analisis = _verificar_precision_pronostico(partido, pronostico)
        
        # Verificar si el pronóstico 1X2 fue acertado
        if partido.pronostico_1x2 and partido.pronostico_1x2_acertado is None:
            goles_local = partido.goles_local or 0
            goles_visitante = partido.goles_visitante or 0
            
            resultado_real = None
            if goles_local > goles_visitante:
                resultado_real = 'local'
            elif goles_visitante > goles_local:
                resultado_real = 'visitante'
            else:
                resultado_real = 'empate'
            
            partido.pronostico_1x2_acertado = (partido.pronostico_1x2 == resultado_real)
            partido.save()
    
    context = {
        'partido': partido,
        'equipo_local': equipo_local,
        'equipo_visitante': equipo_visitante,
        'stats_local': stats_local,
        'stats_visitante': stats_visitante,
        'ultimos_local': ultimos_local,
        'ultimos_visitante': ultimos_visitante,
        'pronostico': pronostico,
        'precision_analisis': precision_analisis,
    }
    
    return render(request, 'ligas/comparacion_equipos.html', context)


def _calcular_estadisticas_equipo(equipo, liga):
    """Calcular estadísticas de un equipo en una liga específica"""
    # Obtener todos los partidos del equipo en esta liga (finalizados)
    partidos = Partido.objects.filter(
        Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
        liga=liga,
        estado='finalizado'
    ).order_by('-fecha', '-jornada')
    
    # Inicializar contadores
    partidos_jugados = 0
    victorias = 0
    empates = 0
    derrotas = 0
    goles_favor = 0
    goles_contra = 0
    goles_favor_local = 0
    goles_contra_local = 0
    goles_favor_visitante = 0
    goles_contra_visitante = 0
    partidos_local = 0
    partidos_visitante = 0
    victorias_local = 0
    victorias_visitante = 0
    
    # Contadores Over/Under
    over_05 = over_15 = over_25 = over_35 = over_45 = 0
    under_05 = under_15 = under_25 = under_35 = under_45 = 0
    
    # Procesar cada partido
    for partido in partidos:
        partidos_jugados += 1
        
        # Determinar si es local o visitante
        es_local = (partido.equipo_local == equipo)
        
        if es_local:
            partidos_local += 1
            goles_eq = partido.goles_local or 0
            goles_rival = partido.goles_visitante or 0
            goles_favor_local += goles_eq
            goles_contra_local += goles_rival
        else:
            partidos_visitante += 1
            goles_eq = partido.goles_visitante or 0
            goles_rival = partido.goles_local or 0
            goles_favor_visitante += goles_eq
            goles_contra_visitante += goles_rival
        
        goles_favor += goles_eq
        goles_contra += goles_rival
        total_goles = goles_eq + goles_rival
        
        # Calcular resultado
        if goles_eq > goles_rival:
            victorias += 1
            if es_local:
                victorias_local += 1
            else:
                victorias_visitante += 1
        elif goles_eq == goles_rival:
            empates += 1
        else:
            derrotas += 1
        
        # Calcular Over/Under
        if total_goles > 0.5:
            over_05 += 1
        else:
            under_05 += 1
            
        if total_goles > 1.5:
            over_15 += 1
        else:
            under_15 += 1
            
        if total_goles > 2.5:
            over_25 += 1
        else:
            under_25 += 1
            
        if total_goles > 3.5:
            over_35 += 1
        else:
            under_35 += 1
            
        if total_goles > 4.5:
            over_45 += 1
        else:
            under_45 += 1
    
    # Calcular estadísticas derivadas
    puntos = (victorias * 3) + empates
    promedio_puntos = round(puntos / partidos_jugados, 2) if partidos_jugados > 0 else 0
    promedio_goles_favor = round(goles_favor / partidos_jugados, 2) if partidos_jugados > 0 else 0
    promedio_goles_contra = round(goles_contra / partidos_jugados, 2) if partidos_jugados > 0 else 0
    promedio_goles = promedio_goles_favor
    porcentaje_victorias = round((victorias / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    promedio_goles_local = round(goles_favor_local / partidos_local, 2) if partidos_local > 0 else 0
    promedio_goles_visitante = round(goles_favor_visitante / partidos_visitante, 2) if partidos_visitante > 0 else 0
    diferencia_goles = goles_favor - goles_contra
    
    # Calcular porcentajes Over/Under
    porcentaje_over_05 = round((over_05 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_under_05 = round((under_05 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_over_15 = round((over_15 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_under_15 = round((under_15 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_over_25 = round((over_25 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_under_25 = round((under_25 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_over_35 = round((over_35 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_under_35 = round((under_35 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_over_45 = round((over_45 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    porcentaje_under_45 = round((under_45 / partidos_jugados) * 100, 1) if partidos_jugados > 0 else 0
    
    return {
        'partidos_jugados': partidos_jugados,
        'victorias': victorias,
        'empates': empates,
        'derrotas': derrotas,
        'goles_favor': goles_favor,
        'goles_contra': goles_contra,
        'goles_favor_local': goles_favor_local,
        'goles_contra_local': goles_contra_local,
        'goles_favor_visitante': goles_favor_visitante,
        'goles_contra_visitante': goles_contra_visitante,
        'partidos_local': partidos_local,
        'partidos_visitante': partidos_visitante,
        'victorias_local': victorias_local,
        'victorias_visitante': victorias_visitante,
        'puntos': puntos,
        'promedio_goles_favor': promedio_goles_favor,
        'promedio_goles_contra': promedio_goles_contra,
        'porcentaje_victorias': porcentaje_victorias,
        'promedio_goles_local': promedio_goles_local,
        'promedio_goles_visitante': promedio_goles_visitante,
        'diferencia_goles': diferencia_goles,
        'promedio_puntos': promedio_puntos,
        'promedio_goles': promedio_goles,
        'over_05': over_05,
        'over_15': over_15,
        'over_25': over_25,
        'over_35': over_35,
        'over_45': over_45,
        'under_05': under_05,
        'under_15': under_15,
        'under_25': under_25,
        'under_35': under_35,
        'under_45': under_45,
        'porcentaje_over_05': porcentaje_over_05,
        'porcentaje_under_05': porcentaje_under_05,
        'porcentaje_over_15': porcentaje_over_15,
        'porcentaje_under_15': porcentaje_under_15,
        'porcentaje_over_25': porcentaje_over_25,
        'porcentaje_under_25': porcentaje_under_25,
        'porcentaje_over_35': porcentaje_over_35,
        'porcentaje_under_35': porcentaje_under_35,
        'porcentaje_over_45': porcentaje_over_45,
        'porcentaje_under_45': porcentaje_under_45,
    }


def _obtener_ultimos_partidos(equipo, liga, cantidad=5):
    """Obtener los últimos N partidos del equipo en una liga específica"""
    partidos = Partido.objects.filter(
        Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
        liga=liga,
        estado='finalizado'
    ).order_by('-fecha', '-jornada')[:cantidad]
    
    ultimos = []
    for partido in partidos:
        if partido.equipo_local == equipo:
            rival = partido.equipo_visitante.nombre
            goles_equipo = partido.goles_local
            goles_rival = partido.goles_visitante
        else:
            rival = partido.equipo_local.nombre
            goles_equipo = partido.goles_visitante
            goles_rival = partido.goles_local
        
        if goles_equipo > goles_rival:
            resultado = 'victoria'
        elif goles_equipo == goles_rival:
            resultado = 'empate'
        else:
            resultado = 'derrota'
        
        ultimos.append({
            'rival': rival,
            'marcador': f'{goles_equipo}-{goles_rival}',
            'resultado': resultado,
            'jornada': partido.jornada,
        })
    
    return ultimos


def _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante):
    """Calcular pronóstico completo basado en estadísticas y forma reciente"""
    
    # Método 1: Promedio de puntos por partido (40% peso)
    puntos_local = stats_local['promedio_puntos']
    puntos_visitante = stats_visitante['promedio_puntos']
    
    # Método 2: Forma reciente - últimos 5 partidos (30% peso)
    forma_local = 0
    for partido in ultimos_local:
        if partido['resultado'] == 'victoria':
            forma_local += 3
        elif partido['resultado'] == 'empate':
            forma_local += 1
    forma_local = forma_local / max(len(ultimos_local), 1)
    
    forma_visitante = 0
    for partido in ultimos_visitante:
        if partido['resultado'] == 'victoria':
            forma_visitante += 3
        elif partido['resultado'] == 'empate':
            forma_visitante += 1
    forma_visitante = forma_visitante / max(len(ultimos_visitante), 1)
    
    # Método 3: Diferencia de goles (20% peso)
    diff_local = stats_local['diferencia_goles'] / max(stats_local['partidos_jugados'], 1)
    diff_visitante = stats_visitante['diferencia_goles'] / max(stats_visitante['partidos_jugados'], 1)
    
    # Método 4: Porcentaje de victorias (10% peso)
    pct_victorias_local = (stats_local['victorias'] / max(stats_local['partidos_jugados'], 1)) * 100
    pct_victorias_visitante = (stats_visitante['victorias'] / max(stats_visitante['partidos_jugados'], 1)) * 100
    
    # Calcular puntuación ponderada
    score_local = (
        puntos_local * 0.4 +
        forma_local * 0.3 +
        diff_local * 0.2 +
        pct_victorias_local * 0.01 +
        0.3  # Factor local (ventaja de casa)
    )
    
    score_visitante = (
        puntos_visitante * 0.4 +
        forma_visitante * 0.3 +
        diff_visitante * 0.2 +
        pct_victorias_visitante * 0.01
    )
    
    # Normalizar a probabilidades (total = 100%)
    total_score = score_local + score_visitante + (abs(score_local - score_visitante) * 0.3)  # Factor empate
    
    prob_local = round((score_local / total_score) * 100, 1)
    prob_visitante = round((score_visitante / total_score) * 100, 1)
    prob_empate = round(100 - prob_local - prob_visitante, 1)
    
    # Ajustar para que sume exactamente 100%
    if prob_empate < 0:
        prob_empate = 0
        total = prob_local + prob_visitante
        prob_local = round((prob_local / total) * 100, 1)
        prob_visitante = 100 - prob_local
    
    # Determinar recomendación
    max_prob = max(prob_local, prob_empate, prob_visitante)
    if max_prob == prob_local:
        recomendacion = 'local'
    elif max_prob == prob_visitante:
        recomendacion = 'visitante'
    else:
        recomendacion = 'empate'
    
    # Calcular doble oportunidad
    doble_local_empate = round(prob_local + prob_empate, 1)
    doble_local_visitante = round(prob_local + prob_visitante, 1)
    doble_empate_visitante = round(prob_empate + prob_visitante, 1)
    
    # Determinar mejor doble oportunidad
    max_doble = max(doble_local_empate, doble_local_visitante, doble_empate_visitante)
    if max_doble == doble_local_empate:
        recomendacion_doble = 'local_empate'
    elif max_doble == doble_empate_visitante:
        recomendacion_doble = 'empate_visitante'
    else:
        recomendacion_doble = 'local_visitante'
    
    # Calcular cuotas aproximadas (cuota = 100 / probabilidad)
    cuota_local = round(100 / prob_local, 2) if prob_local > 0 else 0
    cuota_empate = round(100 / prob_empate, 2) if prob_empate > 0 else 0
    cuota_visitante = round(100 / prob_visitante, 2) if prob_visitante > 0 else 0
    cuota_doble_local_empate = round(100 / doble_local_empate, 2) if doble_local_empate > 0 else 0
    cuota_doble_local_visitante = round(100 / doble_local_visitante, 2) if doble_local_visitante > 0 else 0
    cuota_doble_empate_visitante = round(100 / doble_empate_visitante, 2) if doble_empate_visitante > 0 else 0
    
    # Calcular pronóstico Over/Under combinando estadísticas de ambos equipos
    # Promedio de over 2.5 de ambos equipos
    avg_over_25 = (stats_local['porcentaje_over_25'] + stats_visitante['porcentaje_over_25']) / 2
    avg_under_25 = 100 - avg_over_25
    
    # Ajustar según promedio de goles
    avg_goles_partido = (stats_local['promedio_goles'] + stats_visitante['promedio_goles']) / 2
    
    # Si el promedio combinado es alto, incrementar probabilidad de over
    if avg_goles_partido > 1.5:
        avg_over_25 += 10
    if avg_goles_partido > 2.0:
        avg_over_25 += 5
    
    # Normalizar para que sume 100%
    total_ou = avg_over_25 + avg_under_25
    prob_over_25 = round((avg_over_25 / total_ou) * 100, 1)
    prob_under_25 = round(100 - prob_over_25, 1)
    
    # Calcular para otros límites
    avg_over_05 = (stats_local['porcentaje_over_05'] + stats_visitante['porcentaje_over_05']) / 2
    avg_over_15 = (stats_local['porcentaje_over_15'] + stats_visitante['porcentaje_over_15']) / 2
    avg_over_35 = (stats_local['porcentaje_over_35'] + stats_visitante['porcentaje_over_35']) / 2
    avg_over_45 = (stats_local['porcentaje_over_45'] + stats_visitante['porcentaje_over_45']) / 2
    
    prob_over_05 = round(avg_over_05, 1)
    prob_under_05 = round(100 - prob_over_05, 1)
    prob_over_15 = round(avg_over_15, 1)
    prob_under_15 = round(100 - prob_over_15, 1)
    prob_over_35 = round(avg_over_35, 1)
    prob_under_35 = round(100 - prob_over_35, 1)
    prob_over_45 = round(avg_over_45, 1)
    prob_under_45 = round(100 - prob_over_45, 1)
    
    # Determinar recomendación Over/Under (la opción con mayor probabilidad)
    opciones_ou = {
        'over_05': prob_over_05,
        'over_15': prob_over_15,
        'over_25': prob_over_25,
        'over_35': prob_over_35,
        'over_45': prob_over_45,
        'under_05': prob_under_05,
        'under_15': prob_under_15,
        'under_25': prob_under_25,
        'under_35': prob_under_35,
        'under_45': prob_under_45
    }
    recomendacion_ou = max(opciones_ou, key=opciones_ou.get)
    
    # Calcular cuotas Over/Under
    cuota_over_05 = round(100 / prob_over_05, 2) if prob_over_05 > 0 else 0
    cuota_under_05 = round(100 / prob_under_05, 2) if prob_under_05 > 0 else 0
    cuota_over_15 = round(100 / prob_over_15, 2) if prob_over_15 > 0 else 0
    cuota_under_15 = round(100 / prob_under_15, 2) if prob_under_15 > 0 else 0
    cuota_over_25 = round(100 / prob_over_25, 2) if prob_over_25 > 0 else 0
    cuota_under_25 = round(100 / prob_under_25, 2) if prob_under_25 > 0 else 0
    cuota_over_35 = round(100 / prob_over_35, 2) if prob_over_35 > 0 else 0
    cuota_under_35 = round(100 / prob_under_35, 2) if prob_under_35 > 0 else 0
    cuota_over_45 = round(100 / prob_over_45, 2) if prob_over_45 > 0 else 0
    cuota_under_45 = round(100 / prob_under_45, 2) if prob_under_45 > 0 else 0
    
    # Calcular pronóstico Ambos Marcan (BTTS - Both Teams To Score)
    # Analizar historial de goles de ambos equipos
    local_marca_frecuente = (stats_local['goles_favor'] / max(stats_local['partidos_jugados'], 1)) >= 1.0
    visitante_marca_frecuente = (stats_visitante['goles_favor'] / max(stats_visitante['partidos_jugados'], 1)) >= 1.0
    
    # Calcular probabilidad basada en promedios de goles
    prob_local_marca = min(95, (stats_local['goles_favor'] / max(stats_local['partidos_jugados'], 1)) * 50)
    prob_visitante_marca = min(95, (stats_visitante['goles_favor'] / max(stats_visitante['partidos_jugados'], 1)) * 45)
    
    # Probabilidad de que ambos marquen (combinación de probabilidades)
    prob_ambos_marcan = round(min(95, (prob_local_marca * prob_visitante_marca) / 100), 1)
    
    # Ajustar por defensas débiles (si reciben muchos goles, es más probable que el rival marque)
    if stats_local['goles_contra'] / max(stats_local['partidos_jugados'], 1) > 1.2:
        prob_ambos_marcan += 5
    if stats_visitante['goles_contra'] / max(stats_visitante['partidos_jugados'], 1) > 1.2:
        prob_ambos_marcan += 5
    
    prob_ambos_marcan = min(95, prob_ambos_marcan)
    prob_ambos_no_marcan = round(100 - prob_ambos_marcan, 1)
    
    # Determinar recomendación
    recomendacion_btts = 'si' if prob_ambos_marcan > prob_ambos_no_marcan else 'no'
    
    # Calcular cuotas
    cuota_ambos_si = round(100 / prob_ambos_marcan, 2) if prob_ambos_marcan > 0 else 0
    cuota_ambos_no = round(100 / prob_ambos_no_marcan, 2) if prob_ambos_no_marcan > 0 else 0
    
    # Pronóstico: Resultado Exacto (Score Exacto más probable)
    # Basado en promedios de goles
    goles_local_esperados = round(stats_local['promedio_goles'])
    goles_visitante_esperados = round(stats_visitante['promedio_goles'] * 0.8)  # Factor visitante
    
    # Pronóstico: Margen de Victoria
    diff_puntos = stats_local['promedio_puntos'] - stats_visitante['promedio_puntos']
    if abs(diff_puntos) > 1.0:
        prob_victoria_amplia = 65.0
        prob_victoria_ajustada = 35.0
        margen_recomendado = 'amplia'
    else:
        prob_victoria_amplia = 35.0
        prob_victoria_ajustada = 65.0
        margen_recomendado = 'ajustada'
    
    cuota_victoria_amplia = round(100 / prob_victoria_amplia, 2)
    cuota_victoria_ajustada = round(100 / prob_victoria_ajustada, 2)
    
    # Pronóstico: Victoria Local + Over/Under
    prob_local_over_05 = round((prob_local / 100) * prob_over_05, 1)
    prob_local_over_15 = round((prob_local / 100) * prob_over_15, 1)
    prob_local_over_25 = round((prob_local / 100) * prob_over_25, 1)
    prob_local_under_25 = round((prob_local / 100) * prob_under_25, 1)
    prob_local_under_35 = round((prob_local / 100) * prob_under_35, 1)
    prob_local_under_45 = round((prob_local / 100) * prob_under_45, 1)
    cuota_local_over_05 = round(100 / prob_local_over_05, 2) if prob_local_over_05 > 0 else 0
    cuota_local_over_15 = round(100 / prob_local_over_15, 2) if prob_local_over_15 > 0 else 0
    cuota_local_over_25 = round(100 / prob_local_over_25, 2) if prob_local_over_25 > 0 else 0
    cuota_local_under_25 = round(100 / prob_local_under_25, 2) if prob_local_under_25 > 0 else 0
    cuota_local_under_35 = round(100 / prob_local_under_35, 2) if prob_local_under_35 > 0 else 0
    cuota_local_under_45 = round(100 / prob_local_under_45, 2) if prob_local_under_45 > 0 else 0
    
    # Pronóstico: Victoria Visitante + Over/Under
    prob_visitante_over_05 = round((prob_visitante / 100) * prob_over_05, 1)
    prob_visitante_over_15 = round((prob_visitante / 100) * prob_over_15, 1)
    prob_visitante_over_25 = round((prob_visitante / 100) * prob_over_25, 1)
    prob_visitante_under_25 = round((prob_visitante / 100) * prob_under_25, 1)
    prob_visitante_under_35 = round((prob_visitante / 100) * prob_under_35, 1)
    prob_visitante_under_45 = round((prob_visitante / 100) * prob_under_45, 1)
    cuota_visitante_over_05 = round(100 / prob_visitante_over_05, 2) if prob_visitante_over_05 > 0 else 0
    cuota_visitante_over_15 = round(100 / prob_visitante_over_15, 2) if prob_visitante_over_15 > 0 else 0
    cuota_visitante_over_25 = round(100 / prob_visitante_over_25, 2) if prob_visitante_over_25 > 0 else 0
    cuota_visitante_under_25 = round(100 / prob_visitante_under_25, 2) if prob_visitante_under_25 > 0 else 0
    cuota_visitante_under_35 = round(100 / prob_visitante_under_35, 2) if prob_visitante_under_35 > 0 else 0
    cuota_visitante_under_45 = round(100 / prob_visitante_under_45, 2) if prob_visitante_under_45 > 0 else 0
    
    # Pronóstico: Empate + Over/Under
    prob_empate_over_05 = round((prob_empate / 100) * prob_over_05, 1)
    prob_empate_over_15 = round((prob_empate / 100) * prob_over_15, 1)
    prob_empate_over_25 = round((prob_empate / 100) * prob_over_25, 1)
    prob_empate_under_25 = round((prob_empate / 100) * prob_under_25, 1)
    prob_empate_under_35 = round((prob_empate / 100) * prob_under_35, 1)
    prob_empate_under_45 = round((prob_empate / 100) * prob_under_45, 1)
    cuota_empate_over_05 = round(100 / prob_empate_over_05, 2) if prob_empate_over_05 > 0 else 0
    cuota_empate_over_15 = round(100 / prob_empate_over_15, 2) if prob_empate_over_15 > 0 else 0
    cuota_empate_over_25 = round(100 / prob_empate_over_25, 2) if prob_empate_over_25 > 0 else 0
    cuota_empate_under_25 = round(100 / prob_empate_under_25, 2) if prob_empate_under_25 > 0 else 0
    cuota_empate_under_35 = round(100 / prob_empate_under_35, 2) if prob_empate_under_35 > 0 else 0
    cuota_empate_under_45 = round(100 / prob_empate_under_45, 2) if prob_empate_under_45 > 0 else 0
    
    # Determinar recomendación para Victoria/Empate + Over/Under (el mayor de todos los combos)
    combos_victoria_empate_over = {
        'local_over_05': prob_local_over_05,
        'local_over_15': prob_local_over_15,
        'local_over_25': prob_local_over_25,
        'local_under_25': prob_local_under_25,
        'local_under_35': prob_local_under_35,
        'local_under_45': prob_local_under_45,
        'visitante_over_05': prob_visitante_over_05,
        'visitante_over_15': prob_visitante_over_15,
        'visitante_over_25': prob_visitante_over_25,
        'visitante_under_25': prob_visitante_under_25,
        'visitante_under_35': prob_visitante_under_35,
        'visitante_under_45': prob_visitante_under_45,
        'empate_over_05': prob_empate_over_05,
        'empate_over_15': prob_empate_over_15,
        'empate_over_25': prob_empate_over_25,
        'empate_under_25': prob_empate_under_25,
        'empate_under_35': prob_empate_under_35,
        'empate_under_45': prob_empate_under_45
    }
    recomendacion_victoria_empate_over = max(combos_victoria_empate_over, key=combos_victoria_empate_over.get)
    
    # Pronóstico: Doble Oportunidad + Over/Under
    # 1X (Local o Empate) + Over/Under
    prob_1x_over_15 = round((doble_local_empate / 100) * prob_over_15, 1)
    prob_1x_over_25 = round((doble_local_empate / 100) * prob_over_25, 1)
    prob_1x_under_35 = round((doble_local_empate / 100) * prob_under_35, 1)
    prob_1x_under_45 = round((doble_local_empate / 100) * prob_under_45, 1)
    cuota_1x_over_15 = round(100 / prob_1x_over_15, 2) if prob_1x_over_15 > 0 else 0
    cuota_1x_over_25 = round(100 / prob_1x_over_25, 2) if prob_1x_over_25 > 0 else 0
    cuota_1x_under_35 = round(100 / prob_1x_under_35, 2) if prob_1x_under_35 > 0 else 0
    cuota_1x_under_45 = round(100 / prob_1x_under_45, 2) if prob_1x_under_45 > 0 else 0
    
    # 12 (Local o Visitante) + Over/Under
    prob_12_over_15 = round((doble_local_visitante / 100) * prob_over_15, 1)
    prob_12_over_25 = round((doble_local_visitante / 100) * prob_over_25, 1)
    prob_12_under_35 = round((doble_local_visitante / 100) * prob_under_35, 1)
    prob_12_under_45 = round((doble_local_visitante / 100) * prob_under_45, 1)
    cuota_12_over_15 = round(100 / prob_12_over_15, 2) if prob_12_over_15 > 0 else 0
    cuota_12_over_25 = round(100 / prob_12_over_25, 2) if prob_12_over_25 > 0 else 0
    cuota_12_under_35 = round(100 / prob_12_under_35, 2) if prob_12_under_35 > 0 else 0
    cuota_12_under_45 = round(100 / prob_12_under_45, 2) if prob_12_under_45 > 0 else 0
    
    # X2 (Empate o Visitante) + Over/Under
    prob_x2_over_15 = round((doble_empate_visitante / 100) * prob_over_15, 1)
    prob_x2_over_25 = round((doble_empate_visitante / 100) * prob_over_25, 1)
    prob_x2_under_35 = round((doble_empate_visitante / 100) * prob_under_35, 1)
    prob_x2_under_45 = round((doble_empate_visitante / 100) * prob_under_45, 1)
    cuota_x2_over_15 = round(100 / prob_x2_over_15, 2) if prob_x2_over_15 > 0 else 0
    cuota_x2_over_25 = round(100 / prob_x2_over_25, 2) if prob_x2_over_25 > 0 else 0
    cuota_x2_under_35 = round(100 / prob_x2_under_35, 2) if prob_x2_under_35 > 0 else 0
    cuota_x2_under_45 = round(100 / prob_x2_under_45, 2) if prob_x2_under_45 > 0 else 0
    
    # Determinar recomendación para Doble Oportunidad + Over/Under (el mayor de todos)
    combos_doble_over = {
        '1x_over_15': prob_1x_over_15,
        '1x_over_25': prob_1x_over_25,
        '1x_under_35': prob_1x_under_35,
        '1x_under_45': prob_1x_under_45,
        '12_over_15': prob_12_over_15,
        '12_over_25': prob_12_over_25,
        '12_under_35': prob_12_under_35,
        '12_under_45': prob_12_under_45,
        'x2_over_15': prob_x2_over_15,
        'x2_over_25': prob_x2_over_25,
        'x2_under_35': prob_x2_under_35,
        'x2_under_45': prob_x2_under_45
    }
    recomendacion_doble_over = max(combos_doble_over, key=combos_doble_over.get)
    
    # Pronóstico: Primer Tiempo / Resultado Final
    # Basado en tendencias de rendimiento
    prob_local_local = round(prob_local * 0.7, 1)  # Local gana en ambos tiempos
    prob_empate_local = round(prob_local * 0.3, 1)  # Empate HT, Local gana FT
    prob_local_empate = round(prob_empate * 0.5, 1)  # Local gana HT, Empate FT
    prob_empate_empate = round(prob_empate * 0.5, 1)  # Empate en ambos tiempos
    
    # Pronóstico: Goles en Primera/Segunda Mitad
    prob_goles_1h = 55.0  # Estadísticamente hay más goles en 2H
    prob_goles_2h = 60.0
    prob_mas_goles_1h = 45.0
    prob_mas_goles_2h = 55.0
    
    cuota_goles_1h = round(100 / prob_goles_1h, 2)
    cuota_goles_2h = round(100 / prob_goles_2h, 2)
    cuota_mas_goles_1h = round(100 / prob_mas_goles_1h, 2)
    cuota_mas_goles_2h = round(100 / prob_mas_goles_2h, 2)
    
    mitad_recomendada = '2h' if prob_mas_goles_2h > prob_mas_goles_1h else '1h'
    
    # Pronóstico: Tarjetas (basado en promedio de liga)
    prob_over_35_tarjetas = 48.0
    prob_under_35_tarjetas = 52.0
    cuota_over_tarjetas = round(100 / prob_over_35_tarjetas, 2)
    cuota_under_tarjetas = round(100 / prob_under_35_tarjetas, 2)
    
    # Pronóstico: Córners
    prob_over_9_corners = 52.0
    prob_under_9_corners = 48.0
    cuota_over_corners = round(100 / prob_over_9_corners, 2)
    cuota_under_corners = round(100 / prob_under_9_corners, 2)
    
    # Determinar el MEJOR PRONÓSTICO GENERAL (mayor probabilidad de todos)
    todos_pronosticos = {
        # 1X2
        'Victoria Local': prob_local,
        'Empate': prob_empate,
        'Victoria Visitante': prob_visitante,
        # Doble Oportunidad
        '1X (Local o Empate)': doble_local_empate,
        '12 (Local o Visitante)': doble_local_visitante,
        'X2 (Empate o Visitante)': doble_empate_visitante,
        # Over/Under
        'Over 0.5': prob_over_05,
        'Under 0.5': prob_under_05,
        'Over 1.5': prob_over_15,
        'Under 1.5': prob_under_15,
        'Over 2.5': prob_over_25,
        'Under 2.5': prob_under_25,
        'Over 3.5': prob_over_35,
        'Under 3.5': prob_under_35,
        'Over 4.5': prob_over_45,
        'Under 4.5': prob_under_45,
        # Ambos Marcan
        'Ambos Marcan Sí': prob_ambos_marcan,
        'Ambos Marcan No': prob_ambos_no_marcan,
        # Victoria + Goles
        'Local + Over 0.5': prob_local_over_05,
        'Local + Over 1.5': prob_local_over_15,
        'Local + Over 2.5': prob_local_over_25,
        'Local + Under 2.5': prob_local_under_25,
        'Local + Under 3.5': prob_local_under_35,
        'Local + Under 4.5': prob_local_under_45,
        'Visitante + Over 0.5': prob_visitante_over_05,
        'Visitante + Over 1.5': prob_visitante_over_15,
        'Visitante + Over 2.5': prob_visitante_over_25,
        'Visitante + Under 2.5': prob_visitante_under_25,
        'Visitante + Under 3.5': prob_visitante_under_35,
        'Visitante + Under 4.5': prob_visitante_under_45,
        'Empate + Over 0.5': prob_empate_over_05,
        'Empate + Over 1.5': prob_empate_over_15,
        'Empate + Over 2.5': prob_empate_over_25,
        'Empate + Under 2.5': prob_empate_under_25,
        'Empate + Under 3.5': prob_empate_under_35,
        'Empate + Under 4.5': prob_empate_under_45,
        # Doble Oportunidad + Goles
        '1X + Over 1.5': prob_1x_over_15,
        '1X + Over 2.5': prob_1x_over_25,
        '1X + Under 3.5': prob_1x_under_35,
        '1X + Under 4.5': prob_1x_under_45,
        '12 + Over 1.5': prob_12_over_15,
        '12 + Over 2.5': prob_12_over_25,
        '12 + Under 3.5': prob_12_under_35,
        '12 + Under 4.5': prob_12_under_45,
        'X2 + Over 1.5': prob_x2_over_15,
        'X2 + Over 2.5': prob_x2_over_25,
        'X2 + Under 3.5': prob_x2_under_35,
        'X2 + Under 4.5': prob_x2_under_45,
        # Margen
        'Victoria Amplia': prob_victoria_amplia,
        'Victoria Ajustada': prob_victoria_ajustada,
    }
    
    # Obtener los 3 mejores pronósticos
    top_3_pronosticos = sorted(todos_pronosticos.items(), key=lambda x: x[1], reverse=True)[:3]
    
    mejores_pronosticos = []
    for i, (nombre, prob) in enumerate(top_3_pronosticos, 1):
        cuota = round(100 / prob, 2) if prob > 0 else 0
        mejores_pronosticos.append({
            'posicion': i,
            'nombre': nombre,
            'probabilidad': prob,
            'cuota': cuota
        })
    
    return {
        'prob_local': prob_local,
        'prob_empate': prob_empate,
        'prob_visitante': prob_visitante,
        'recomendacion': recomendacion,
        'confianza': round(max_prob, 1),
        'cuota_local': cuota_local,
        'cuota_empate': cuota_empate,
        'cuota_visitante': cuota_visitante,
        'doble_local_empate': doble_local_empate,
        'doble_local_visitante': doble_local_visitante,
        'doble_empate_visitante': doble_empate_visitante,
        'recomendacion_doble': recomendacion_doble,
        'cuota_doble_local_empate': cuota_doble_local_empate,
        'cuota_doble_local_visitante': cuota_doble_local_visitante,
        'cuota_doble_empate_visitante': cuota_doble_empate_visitante,
        'prob_over_05': prob_over_05,
        'prob_under_05': prob_under_05,
        'prob_over_15': prob_over_15,
        'prob_under_15': prob_under_15,
        'prob_over_25': prob_over_25,
        'prob_under_25': prob_under_25,
        'prob_over_35': prob_over_35,
        'prob_under_35': prob_under_35,
        'prob_over_45': prob_over_45,
        'prob_under_45': prob_under_45,
        'cuota_over_05': cuota_over_05,
        'cuota_under_05': cuota_under_05,
        'cuota_over_15': cuota_over_15,
        'cuota_under_15': cuota_under_15,
        'cuota_over_25': cuota_over_25,
        'cuota_under_25': cuota_under_25,
        'cuota_over_35': cuota_over_35,
        'cuota_under_35': cuota_under_35,
        'cuota_over_45': cuota_over_45,
        'cuota_under_45': cuota_under_45,
        'recomendacion_ou': recomendacion_ou,
        'prob_ambos_marcan': prob_ambos_marcan,
        'prob_ambos_no_marcan': prob_ambos_no_marcan,
        'cuota_ambos_si': cuota_ambos_si,
        'cuota_ambos_no': cuota_ambos_no,
        'recomendacion_btts': recomendacion_btts,
        'score_exacto_local': goles_local_esperados,
        'score_exacto_visitante': goles_visitante_esperados,
        'prob_victoria_amplia': prob_victoria_amplia,
        'prob_victoria_ajustada': prob_victoria_ajustada,
        'cuota_victoria_amplia': cuota_victoria_amplia,
        'cuota_victoria_ajustada': cuota_victoria_ajustada,
        'margen_recomendado': margen_recomendado,
        'prob_local_over_05': prob_local_over_05,
        'cuota_local_over_05': cuota_local_over_05,
        'prob_local_over_15': prob_local_over_15,
        'prob_local_over_25': prob_local_over_25,
        'cuota_local_over_15': cuota_local_over_15,
        'cuota_local_over_25': cuota_local_over_25,
        'prob_local_under_25': prob_local_under_25,
        'prob_local_under_35': prob_local_under_35,
        'prob_local_under_45': prob_local_under_45,
        'cuota_local_under_25': cuota_local_under_25,
        'cuota_local_under_35': cuota_local_under_35,
        'cuota_local_under_45': cuota_local_under_45,
        'prob_visitante_over_05': prob_visitante_over_05,
        'cuota_visitante_over_05': cuota_visitante_over_05,
        'prob_visitante_over_15': prob_visitante_over_15,
        'prob_visitante_over_25': prob_visitante_over_25,
        'cuota_visitante_over_15': cuota_visitante_over_15,
        'cuota_visitante_over_25': cuota_visitante_over_25,
        'prob_visitante_under_25': prob_visitante_under_25,
        'prob_visitante_under_35': prob_visitante_under_35,
        'prob_visitante_under_45': prob_visitante_under_45,
        'cuota_visitante_under_25': cuota_visitante_under_25,
        'cuota_visitante_under_35': cuota_visitante_under_35,
        'cuota_visitante_under_45': cuota_visitante_under_45,
        'prob_empate_over_05': prob_empate_over_05,
        'cuota_empate_over_05': cuota_empate_over_05,
        'prob_empate_over_15': prob_empate_over_15,
        'prob_empate_over_25': prob_empate_over_25,
        'cuota_empate_over_15': cuota_empate_over_15,
        'cuota_empate_over_25': cuota_empate_over_25,
        'prob_empate_under_25': prob_empate_under_25,
        'prob_empate_under_35': prob_empate_under_35,
        'prob_empate_under_45': prob_empate_under_45,
        'cuota_empate_under_25': cuota_empate_under_25,
        'cuota_empate_under_35': cuota_empate_under_35,
        'cuota_empate_under_45': cuota_empate_under_45,
        'recomendacion_victoria_empate_over': recomendacion_victoria_empate_over,
        'prob_1x_over_15': prob_1x_over_15,
        'prob_1x_over_25': prob_1x_over_25,
        'prob_1x_under_35': prob_1x_under_35,
        'prob_1x_under_45': prob_1x_under_45,
        'cuota_1x_over_15': cuota_1x_over_15,
        'cuota_1x_over_25': cuota_1x_over_25,
        'cuota_1x_under_35': cuota_1x_under_35,
        'cuota_1x_under_45': cuota_1x_under_45,
        'prob_12_over_15': prob_12_over_15,
        'prob_12_over_25': prob_12_over_25,
        'prob_12_under_35': prob_12_under_35,
        'prob_12_under_45': prob_12_under_45,
        'cuota_12_over_15': cuota_12_over_15,
        'cuota_12_over_25': cuota_12_over_25,
        'cuota_12_under_35': cuota_12_under_35,
        'cuota_12_under_45': cuota_12_under_45,
        'prob_x2_over_15': prob_x2_over_15,
        'prob_x2_over_25': prob_x2_over_25,
        'prob_x2_under_35': prob_x2_under_35,
        'prob_x2_under_45': prob_x2_under_45,
        'cuota_x2_over_15': cuota_x2_over_15,
        'cuota_x2_over_25': cuota_x2_over_25,
        'cuota_x2_under_35': cuota_x2_under_35,
        'cuota_x2_under_45': cuota_x2_under_45,
        'recomendacion_doble_over': recomendacion_doble_over,
        'prob_local_local': prob_local_local,
        'prob_empate_local': prob_empate_local,
        'prob_local_empate': prob_local_empate,
        'prob_empate_empate': prob_empate_empate,
        'prob_goles_1h': prob_goles_1h,
        'prob_goles_2h': prob_goles_2h,
        'prob_mas_goles_1h': prob_mas_goles_1h,
        'prob_mas_goles_2h': prob_mas_goles_2h,
        'cuota_goles_1h': cuota_goles_1h,
        'cuota_goles_2h': cuota_goles_2h,
        'cuota_mas_goles_1h': cuota_mas_goles_1h,
        'cuota_mas_goles_2h': cuota_mas_goles_2h,
        'mitad_recomendada': mitad_recomendada,
        'prob_over_35_tarjetas': prob_over_35_tarjetas,
        'prob_under_35_tarjetas': prob_under_35_tarjetas,
        'cuota_over_tarjetas': cuota_over_tarjetas,
        'cuota_under_tarjetas': cuota_under_tarjetas,
        'prob_over_9_corners': prob_over_9_corners,
        'prob_under_9_corners': prob_under_9_corners,
        'cuota_over_corners': cuota_over_corners,
        'cuota_under_corners': cuota_under_corners,
        'mejores_pronosticos': mejores_pronosticos,
        'metodo': 'Análisis Multifactorial: Promedio puntos (40%), Forma reciente (30%), Diferencia goles (20%), % Victorias (10%), Factor local'
    }


def _verificar_precision_pronostico(partido, pronostico):
    """Verifica la precisión del pronóstico comparándolo con el resultado real"""
    goles_local = partido.goles_local or 0
    goles_visitante = partido.goles_visitante or 0
    total_goles = goles_local + goles_visitante
    
    aciertos = []
    errores = []
    
    # 1X2 - Resultado del partido
    resultado_real = None
    if goles_local > goles_visitante:
        resultado_real = 'local'
    elif goles_visitante > goles_local:
        resultado_real = 'visitante'
    else:
        resultado_real = 'empate'
    
    if pronostico['recomendacion'] == resultado_real:
        aciertos.append({
            'categoria': 'Resultado 1X2',
            'pronostico': f'Victoria {pronostico["recomendacion"].title()}',
            'real': f'Victoria {resultado_real.title()}',
            'prob': pronostico[f'prob_{pronostico["recomendacion"]}']
        })
    else:
        errores.append({
            'categoria': 'Resultado 1X2',
            'pronostico': f'Victoria {pronostico["recomendacion"].title()}',
            'real': f'Victoria {resultado_real.title()}',
            'prob': pronostico[f'prob_{pronostico["recomendacion"]}']
        })
    
    # Doble Oportunidad
    recomendacion_doble = pronostico['recomendacion_doble']
    acierta_doble = False
    if recomendacion_doble == 'local_empate' and resultado_real in ['local', 'empate']:
        acierta_doble = True
    elif recomendacion_doble == 'local_visitante' and resultado_real in ['local', 'visitante']:
        acierta_doble = True
    elif recomendacion_doble == 'empate_visitante' and resultado_real in ['empate', 'visitante']:
        acierta_doble = True
    
    if acierta_doble:
        aciertos.append({
            'categoria': 'Doble Oportunidad',
            'pronostico': recomendacion_doble.upper().replace('_', ' o '),
            'real': f'{resultado_real.title()}',
            'prob': pronostico[f'doble_{recomendacion_doble}']
        })
    else:
        errores.append({
            'categoria': 'Doble Oportunidad',
            'pronostico': recomendacion_doble.upper().replace('_', ' o '),
            'real': f'{resultado_real.title()}',
            'prob': pronostico[f'doble_{recomendacion_doble}']
        })
    
    # Over/Under - Verificar cada umbral
    umbrales_ou = [
        ('0.5', 0.5), ('1.5', 1.5), ('2.5', 2.5), ('3.5', 3.5), ('4.5', 4.5)
    ]
    
    for nombre, umbral in umbrales_ou:
        # Over
        real_over = total_goles > umbral
        nombre_clean = nombre.replace('.', '')
        prob_over = pronostico.get(f'prob_over_{nombre_clean}', 0)
        prob_under = pronostico.get(f'prob_under_{nombre_clean}', 0)
        
        if prob_over > prob_under:  # Pronosticó Over
            if real_over:
                aciertos.append({
                    'categoria': f'Over/Under {nombre}',
                    'pronostico': f'Over {nombre}',
                    'real': f'Over {nombre} ({total_goles} goles)',
                    'prob': prob_over
                })
            else:
                errores.append({
                    'categoria': f'Over/Under {nombre}',
                    'pronostico': f'Over {nombre}',
                    'real': f'Under {nombre} ({total_goles} goles)',
                    'prob': prob_over
                })
        else:  # Pronosticó Under
            if not real_over:
                aciertos.append({
                    'categoria': f'Over/Under {nombre}',
                    'pronostico': f'Under {nombre}',
                    'real': f'Under {nombre} ({total_goles} goles)',
                    'prob': prob_under
                })
            else:
                errores.append({
                    'categoria': f'Over/Under {nombre}',
                    'pronostico': f'Under {nombre}',
                    'real': f'Over {nombre} ({total_goles} goles)',
                    'prob': prob_under
                })
    
    # Ambos Marcan
    ambos_marcan_real = goles_local > 0 and goles_visitante > 0
    if pronostico['recomendacion_btts'] == 'si':
        if ambos_marcan_real:
            aciertos.append({
                'categoria': 'Ambos Marcan',
                'pronostico': 'Sí',
                'real': f'Sí ({goles_local}-{goles_visitante})',
                'prob': pronostico['prob_ambos_marcan']
            })
        else:
            errores.append({
                'categoria': 'Ambos Marcan',
                'pronostico': 'Sí',
                'real': f'No ({goles_local}-{goles_visitante})',
                'prob': pronostico['prob_ambos_marcan']
            })
    else:
        if not ambos_marcan_real:
            aciertos.append({
                'categoria': 'Ambos Marcan',
                'pronostico': 'No',
                'real': f'No ({goles_local}-{goles_visitante})',
                'prob': pronostico['prob_ambos_no_marcan']
            })
        else:
            errores.append({
                'categoria': 'Ambos Marcan',
                'pronostico': 'No',
                'real': f'Sí ({goles_local}-{goles_visitante})',
                'prob': pronostico['prob_ambos_no_marcan']
            })
    
    # Resultado Exacto
    goles_local_esperado = pronostico.get('score_exacto_local', 0)
    goles_visitante_esperado = pronostico.get('score_exacto_visitante', 0)
    
    if goles_local == goles_local_esperado and goles_visitante == goles_visitante_esperado:
        aciertos.append({
            'categoria': 'Resultado Exacto',
            'pronostico': f'{goles_local_esperado}-{goles_visitante_esperado}',
            'real': f'{goles_local}-{goles_visitante}',
            'prob': 100
        })
    else:
        errores.append({
            'categoria': 'Resultado Exacto',
            'pronostico': f'{goles_local_esperado}-{goles_visitante_esperado}',
            'real': f'{goles_local}-{goles_visitante}',
            'prob': 100
        })
    
    # Calcular porcentaje de aciertos
    total_pronosticos = len(aciertos) + len(errores)
    porcentaje_aciertos = round((len(aciertos) / total_pronosticos * 100), 1) if total_pronosticos > 0 else 0
    
    # Verificar si los TOP 3 mejores pronósticos acertaron
    top_3_verificacion = []
    for mejor in pronostico.get('mejores_pronosticos', []):
        nombre = mejor['nombre']
        prob = mejor['probabilidad']
        acierto = False
        
        # Verificar según el tipo de pronóstico
        if 'Victoria Local' in nombre and resultado_real == 'local':
            acierto = True
        elif 'Victoria Visitante' in nombre and resultado_real == 'visitante':
            acierto = True
        elif nombre == 'Empate' and resultado_real == 'empate':
            acierto = True
        elif '1X' in nombre and resultado_real in ['local', 'empate']:
            acierto = True
        elif '12' in nombre and resultado_real in ['local', 'visitante']:
            acierto = True
        elif 'X2' in nombre and resultado_real in ['empate', 'visitante']:
            acierto = True
        elif 'Over' in nombre:
            umbral = float(nombre.split()[-1])
            if total_goles > umbral:
                acierto = True
        elif 'Under' in nombre:
            umbral = float(nombre.split()[-1])
            if total_goles <= umbral:
                acierto = True
        elif 'Ambos Marcan Sí' in nombre:
            if goles_local > 0 and goles_visitante > 0:
                acierto = True
        elif 'Ambos Marcan No' in nombre:
            if not (goles_local > 0 and goles_visitante > 0):
                acierto = True
        elif 'Local +' in nombre:
            if resultado_real == 'local':
                if 'Over' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles > umbral:
                        acierto = True
                elif 'Under' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles <= umbral:
                        acierto = True
        elif 'Visitante +' in nombre:
            if resultado_real == 'visitante':
                if 'Over' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles > umbral:
                        acierto = True
                elif 'Under' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles <= umbral:
                        acierto = True
        elif 'Empate +' in nombre:
            if resultado_real == 'empate':
                if 'Over' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles > umbral:
                        acierto = True
                elif 'Under' in nombre:
                    umbral = float(nombre.split()[-1])
                    if total_goles <= umbral:
                        acierto = True
        
        top_3_verificacion.append({
            'posicion': mejor['posicion'],
            'nombre': nombre,
            'probabilidad': prob,
            'cuota': mejor['cuota'],
            'acierto': acierto
        })
    
    # Calcular precisión del TOP 3
    aciertos_top3 = sum(1 for t in top_3_verificacion if t['acierto'])
    total_top3 = len(top_3_verificacion)
    precision_top3 = round((aciertos_top3 / total_top3 * 100), 1) if total_top3 > 0 else 0
    
    return {
        'aciertos': aciertos,
        'errores': errores,
        'total_aciertos': len(aciertos),
        'total_errores': len(errores),
        'total_pronosticos': total_pronosticos,
        'porcentaje_aciertos': porcentaje_aciertos,
        'resultado_real': f'{goles_local} - {goles_visitante}',
        'total_goles_real': total_goles,
        'top_3_verificacion': top_3_verificacion,
        'aciertos_top3': aciertos_top3,
        'total_top3': total_top3,
        'precision_top3': precision_top3
    }


def reporte_pronosticos_pdf(request):
    """Genera un PDF con los TOP 3 pronósticos de partidos programados filtrados por fecha"""
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from django.http import HttpResponse
    from datetime import datetime, timedelta
    
    # Obtener parámetros de filtro
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    # Si no hay fechas, usar hoy y mañana por defecto
    if not fecha_desde:
        fecha_desde = datetime.now().date()
    else:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
    
    if not fecha_hasta:
        fecha_hasta = fecha_desde + timedelta(days=1)
    else:
        fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
    
    # Crear respuesta HTTP con PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="pronosticos_{fecha_desde}_{fecha_hasta}.pdf"'
    
    # Crear documento PDF
    doc = SimpleDocTemplate(response, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados compactos
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#0f1923'),
        spaceAfter=10,
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#243447'),
        spaceAfter=6,
        alignment=TA_LEFT
    )
    
    text_style = ParagraphStyle(
        'SmallText',
        parent=styles['Normal'],
        fontSize=8,
        leading=10
    )
    
    # Título del reporte
    elements.append(Paragraph(f'⚽ PRONÓSTICOS DEPORTIVOS', title_style))
    elements.append(Paragraph(f'{fecha_desde.strftime("%d/%m/%Y")} - {fecha_hasta.strftime("%d/%m/%Y")}', text_style))
    elements.append(Spacer(1, 0.15*inch))
    
    # Obtener todas las ligas activas con su precisión
    ligas = Liga.objects.filter(activa=True)
    ligas_con_precision = []
    
    for liga in ligas:
        # Calcular precisión de la liga (últimos 10 partidos)
        # Usando servicios optimizados con caché automático
        precision_promedio = 0
        precision_top3_promedio = 0
        partidos_con_precision = 0
        partidos_finalizados = liga.partidos.filter(
            estado='finalizado',
            goles_local__isnull=False,
            goles_visitante__isnull=False
        ).order_by('-fecha', '-jornada')[:10]
        
        for partido in partidos_finalizados:
            try:
                # Calcular estadísticas
                stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                
                # Calcular pronóstico
                pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                
                # Verificar precisión
                precision_analisis = _verificar_precision_pronostico(partido, pronostico)
                precision_promedio += precision_analisis['porcentaje_aciertos']
                
                if precision_analisis.get('precision_top3') is not None:
                    precision_top3_promedio += precision_analisis['precision_top3']
                
                partidos_con_precision += 1
            except Exception:
                continue
        
        if partidos_con_precision > 0:
            precision_promedio = round(precision_promedio / partidos_con_precision, 1)
            precision_top3_promedio = round(precision_top3_promedio / partidos_con_precision, 1)
        
        ligas_con_precision.append({
            'liga': liga,
            'precision': precision_promedio,
            'precision_top3': precision_top3_promedio
        })
    
    # Ordenar ligas por precisión TOP 3 (mayor a menor)
    ligas_con_precision.sort(key=lambda x: x['precision_top3'], reverse=True)
    
    # Obtener partidos programados en el rango de fechas
    total_partidos = 0
    
    for liga_data in ligas_con_precision:
        liga = liga_data['liga']
        precision = liga_data['precision']
        precision_top3 = liga_data['precision_top3']
        
        partidos = liga.partidos.filter(
            estado='programado',
            fecha__gte=fecha_desde,
            fecha__lte=fecha_hasta
        ).order_by('fecha', 'jornada')
        
        if not partidos.exists():
            continue
        
        # Título de la liga con país (compacto)
        pais_text = f' ({liga.pais})' if liga.pais else ''
        elements.append(Paragraph(
            f'🏆 {liga.nombre}{pais_text} - Precisión General: {precision}% | TOP 3: {precision_top3}%', 
            subtitle_style
        ))
        elements.append(Spacer(1, 0.05*inch))
        
        # Preparar datos para tabla de múltiples columnas
        partidos_data = []
        
        for partido in partidos:
            total_partidos += 1
            
            try:
                # Calcular estadísticas
                stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                
                # Calcular pronóstico
                pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                
                # Información del partido (compacta)
                fecha_str = partido.fecha.strftime('%d/%m %H:%M') if partido.fecha else 'TBD'
                
                # Construir texto del partido con TOP 3
                partido_text = f'<b>{partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre}</b><br/>{fecha_str}<br/>'
                
                for i, mejor in enumerate(pronostico.get('mejores_pronosticos', []), 1):
                    medalla = '🥇' if i == 1 else '🥈' if i == 2 else '🥉'
                    partido_text += f'{medalla} {mejor["nombre"]}: {mejor["probabilidad"]}% ({mejor["cuota"]})<br/>'
                
                partidos_data.append(Paragraph(partido_text, text_style))
                
            except Exception as e:
                continue
        
        # Crear tabla con 2 columnas de partidos
        if partidos_data:
            # Organizar en filas de 2 columnas
            rows = []
            for i in range(0, len(partidos_data), 2):
                if i + 1 < len(partidos_data):
                    rows.append([partidos_data[i], partidos_data[i + 1]])
                else:
                    rows.append([partidos_data[i], ''])
            
            tabla_liga = Table(rows, colWidths=[3.5*inch, 3.5*inch])
            tabla_liga.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#243447')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            elements.append(tabla_liga)
        
        elements.append(Spacer(1, 0.15*inch))
    
    # Si no hay partidos
    if total_partidos == 0:
        elements.append(Paragraph(
            f'Sin partidos programados en estas fechas',
            text_style
        ))
    else:
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph(f'<b>Total: {total_partidos} partidos</b>', text_style))
    
    # Generar PDF
    doc.build(elements)
    
    return response


def enviar_reporte_whatsapp(request):
    """Envía el reporte PDF por WhatsApp usando Twilio"""
    from twilio.rest import Client
    from django.conf import settings
    from django.http import JsonResponse
    import os
    from datetime import datetime, timedelta
    
    print("=== INICIO enviar_reporte_whatsapp ===")
    print(f"Método: {request.method}")
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    # Obtener parámetros
    telefono = request.POST.get('telefono', '')
    fecha_desde = request.POST.get('fecha_desde', '')
    fecha_hasta = request.POST.get('fecha_hasta', '')
    
    print(f"Teléfono recibido: {telefono}")
    print(f"Fechas: {fecha_desde} - {fecha_hasta}")
    
    if not telefono:
        return JsonResponse({'error': 'Número de teléfono requerido'}, status=400)
    
    # Validar formato de teléfono (debe incluir código de país, ej: +51999999999)
    if not telefono.startswith('+'):
        telefono = '+' + telefono
    
    try:
        # Configuración de Twilio (agregar en settings.py)
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        whatsapp_from = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
        
        if not account_sid or not auth_token:
            return JsonResponse({
                'error': 'Configuración de Twilio no encontrada. Agregar TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN en settings.py'
            }, status=500)
        
        client = Client(account_sid, auth_token)
        
        # Si no hay fechas, usar hoy y mañana por defecto
        if not fecha_desde:
            fecha_desde = datetime.now().date()
        else:
            fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
        
        if not fecha_hasta:
            fecha_hasta = fecha_desde + timedelta(days=1)
        else:
            fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
        
        # Generar el PDF en memoria
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Estilos (reutilizar los mismos del PDF)
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14, 
                                     textColor=colors.HexColor('#0f1923'), spaceAfter=10, alignment=TA_CENTER)
        subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Heading2'], fontSize=10,
                                       textColor=colors.HexColor('#243447'), spaceAfter=6, alignment=TA_LEFT)
        text_style = ParagraphStyle('SmallText', parent=styles['Normal'], fontSize=8, leading=10)
        
        elements.append(Paragraph(f'⚽ PRONÓSTICOS DEPORTIVOS', title_style))
        elements.append(Paragraph(f'{fecha_desde.strftime("%d/%m/%Y")} - {fecha_hasta.strftime("%d/%m/%Y")}', text_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Obtener ligas y partidos (misma lógica que reporte_pronosticos_pdf)
        ligas = Liga.objects.filter(activa=True)
        ligas_con_precision = []
        
        for liga in ligas:
            # Calcular precisión de la liga usando servicios optimizados
            precision_promedio = 0
            precision_top3_promedio = 0
            partidos_con_precision = 0
            partidos_finalizados = liga.partidos.filter(
                estado='finalizado', goles_local__isnull=False, goles_visitante__isnull=False
            ).order_by('-fecha', '-jornada')[:10]
            
            for partido in partidos_finalizados:
                try:
                    # Calcular estadísticas
                    stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                    stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                    ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                    ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                    
                    # Calcular pronóstico
                    pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                    
                    # Verificar precisión
                    precision_analisis = _verificar_precision_pronostico(partido, pronostico)
                    precision_promedio += precision_analisis['porcentaje_aciertos']
                    
                    if precision_analisis.get('precision_top3') is not None:
                        precision_top3_promedio += precision_analisis['precision_top3']
                    
                    partidos_con_precision += 1
                except Exception:
                    continue
            
            if partidos_con_precision > 0:
                precision_promedio = round(precision_promedio / partidos_con_precision, 1)
                precision_top3_promedio = round(precision_top3_promedio / partidos_con_precision, 1)
            
            ligas_con_precision.append({'liga': liga, 'precision': precision_promedio, 'precision_top3': precision_top3_promedio})
        
        ligas_con_precision.sort(key=lambda x: x['precision_top3'], reverse=True)
        
        total_partidos = 0
        
        for liga_data in ligas_con_precision:
            liga = liga_data['liga']
            precision = liga_data['precision']
            precision_top3 = liga_data['precision_top3']
            
            partidos = liga.partidos.filter(
                estado='programado', fecha__gte=fecha_desde, fecha__lte=fecha_hasta
            ).order_by('fecha', 'jornada')
            
            if not partidos.exists():
                continue
            
            pais_text = f' ({liga.pais})' if liga.pais else ''
            elements.append(Paragraph(f'🏆 {liga.nombre}{pais_text} - Precisión General: {precision}% | TOP 3: {precision_top3}%', subtitle_style))
            elements.append(Spacer(1, 0.05*inch))
            
            partidos_data = []
            
            for partido in partidos:
                total_partidos += 1
                try:
                    # Calcular estadísticas
                    stats_local = _calcular_estadisticas_equipo(partido.equipo_local, liga)
                    stats_visitante = _calcular_estadisticas_equipo(partido.equipo_visitante, liga)
                    ultimos_local = _obtener_ultimos_partidos(partido.equipo_local, liga, 5)
                    ultimos_visitante = _obtener_ultimos_partidos(partido.equipo_visitante, liga, 5)
                    
                    # Calcular pronóstico
                    pronostico = _calcular_pronostico(stats_local, stats_visitante, ultimos_local, ultimos_visitante)
                    
                    fecha_str = partido.fecha.strftime('%d/%m %H:%M') if partido.fecha else 'TBD'
                    partido_text = f'<b>{partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre}</b><br/>{fecha_str}<br/>'
                    
                    for i, mejor in enumerate(pronostico.get('mejores_pronosticos', []), 1):
                        medalla = '🥇' if i == 1 else '🥈' if i == 2 else '🥉'
                        partido_text += f'{medalla} {mejor["nombre"]}: {mejor["probabilidad"]}% ({mejor["cuota"]})<br/>'
                    
                    partidos_data.append(Paragraph(partido_text, text_style))
                except Exception:
                    continue
            
            if partidos_data:
                rows = []
                for i in range(0, len(partidos_data), 2):
                    if i + 1 < len(partidos_data):
                        rows.append([partidos_data[i], partidos_data[i + 1]])
                    else:
                        rows.append([partidos_data[i], ''])
                
                tabla_liga = Table(rows, colWidths=[3.5*inch, 3.5*inch])
                tabla_liga.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#243447')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                elements.append(tabla_liga)
            
            elements.append(Spacer(1, 0.15*inch))
        
        if total_partidos == 0:
            elements.append(Paragraph('Sin partidos programados en estas fechas', text_style))
        else:
            elements.append(Spacer(1, 0.1*inch))
            elements.append(Paragraph(f'<b>Total: {total_partidos} partidos</b>', text_style))
        
        doc.build(elements)
        buffer.seek(0)
        
        # Guardar PDF temporalmente
        temp_filename = f'pronosticos_{fecha_desde}_{fecha_hasta}.pdf'
        temp_path = os.path.join(settings.MEDIA_ROOT if hasattr(settings, 'MEDIA_ROOT') else '/tmp', temp_filename)
        
        with open(temp_path, 'wb') as f:
            f.write(buffer.getvalue())
        
        # Enviar por WhatsApp
        print(f"Intentando enviar WhatsApp a: whatsapp:{telefono}")
        print(f"Desde: {whatsapp_from}")
        
        try:
            message = client.messages.create(
                from_=whatsapp_from,
                body=f'📊 Reporte de Pronósticos\n{fecha_desde.strftime("%d/%m/%Y")} - {fecha_hasta.strftime("%d/%m/%Y")}\nTotal: {total_partidos} partidos',
                to=f'whatsapp:{telefono}'
            )
            
            print(f"✅ Mensaje enviado exitosamente. SID: {message.sid}")
            
            return JsonResponse({
                'success': True,
                'message': f'Reporte enviado exitosamente a {telefono}',
                'sid': message.sid
            })
        except Exception as twilio_error:
            error_msg = str(twilio_error)
            print(f"❌ Error de Twilio: {error_msg}")
            
            if '63007' in error_msg or 'Channel' in error_msg or 'not found' in error_msg.lower():
                return JsonResponse({
                    'error': '⚠️ PRIMERO ACTIVA WHATSAPP SANDBOX:\n\n1. Abre tu WhatsApp\n2. Envía este mensaje: join thrown-identity\n3. Al número: +1 415 523 8886\n4. Espera el mensaje de confirmación\n5. Luego intenta de nuevo aquí'
                }, status=400)
            elif '21211' in error_msg or 'invalid' in error_msg.lower():
                return JsonResponse({
                    'error': f'Número inválido: {telefono}. Debe incluir código de país (ej: +51999999999)'
                }, status=400)
            else:
                return JsonResponse({'error': f'Error de Twilio: {error_msg}'}, status=500)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def partidos_en_vivo_api(request):
    """API para obtener partidos próximos y finalizados hoy"""
    from django.http import JsonResponse
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    ahora = timezone.now()
    hoy_inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoy_fin = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)
    proximas_2h = ahora + timedelta(hours=2)
    
    # Partidos en progreso
    partidos_en_progreso = Partido.objects.filter(
        estado='en_progreso'
    ).select_related('equipo_local', 'equipo_visitante', 'liga').order_by('fecha')
    
    # Partidos próximos (próximas 2 horas)
    partidos_proximos = Partido.objects.filter(
        estado='programado',
        fecha__gte=ahora,
        fecha__lte=proximas_2h
    ).select_related('equipo_local', 'equipo_visitante', 'liga').order_by('fecha')
    
    # Partidos finalizados hoy
    partidos_finalizados = Partido.objects.filter(
        estado='finalizado',
        fecha__gte=hoy_inicio,
        fecha__lte=hoy_fin
    ).select_related('equipo_local', 'equipo_visitante', 'liga').order_by('-fecha')
    
    en_progreso_data = []
    for partido in partidos_en_progreso:
        en_progreso_data.append({
            'id': partido.id,
            'local': partido.equipo_local.nombre,
            'visitante': partido.equipo_visitante.nombre,
            'liga': partido.liga.nombre,
            'liga_id': partido.liga.id,
            'resultado': f'{partido.goles_local}-{partido.goles_visitante}' if partido.goles_local is not None else '0-0'
        })
    
    proximos_data = []
    for partido in partidos_proximos:
        proximos_data.append({
            'id': partido.id,
            'local': partido.equipo_local.nombre,
            'visitante': partido.equipo_visitante.nombre,
            'liga': partido.liga.nombre,
            'liga_id': partido.liga.id,
            'fecha': partido.fecha.strftime('%H:%M') if partido.fecha else 'TBD'
        })
    
    finalizados_data = []
    for partido in partidos_finalizados:
        finalizados_data.append({
            'id': partido.id,
            'local': partido.equipo_local.nombre,
            'visitante': partido.equipo_visitante.nombre,
            'liga': partido.liga.nombre,
            'liga_id': partido.liga.id,
            'resultado': f'{partido.goles_local}-{partido.goles_visitante}' if partido.goles_local is not None else ''
        })
    
    return JsonResponse({
        'en_progreso': en_progreso_data,
        'proximos': proximos_data,
        'finalizados': finalizados_data
    })


def partidos_en_juego_api(request, liga_id):
    """API para obtener partidos en juego de una liga específica"""
    liga = get_object_or_404(Liga, id=liga_id)
    
    partidos_en_juego = liga.partidos.filter(
        estado='en_juego'
    ).select_related('equipo_local', 'equipo_visitante')
    
    partidos_data = []
    for partido in partidos_en_juego:
        partidos_data.append({
            'id': partido.id,
            'jornada': partido.jornada,
            'equipo_local': partido.equipo_local.nombre,
            'equipo_visitante': partido.equipo_visitante.nombre,
            'goles_local': partido.goles_local if partido.goles_local is not None else 0,
            'goles_visitante': partido.goles_visitante if partido.goles_visitante is not None else 0,
            'estado': partido.estado,
        })
    
    return JsonResponse({
        'partidos': partidos_data,
        'count': len(partidos_data)
    })
