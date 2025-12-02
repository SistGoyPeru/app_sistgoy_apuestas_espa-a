from django.urls import path
from . import views

app_name = 'ligas'

urlpatterns = [
    path('', views.home, name='home'),
    path('agregar-liga/', views.agregar_liga, name='agregar_liga'),
    path('liga/<int:liga_id>/partidos/', views.lista_partidos, name='lista_partidos'),
    path('liga/<int:liga_id>/estadisticas/', views.estadisticas, name='estadisticas'),
    path('liga/<int:liga_id>/estadisticas-completas/', views.estadisticas_completas, name='estadisticas_completas'),
    path('liga/<int:liga_id>/editar/', views.editar_liga, name='editar_liga'),
    path('liga/<int:liga_id>/actualizar/', views.actualizar_liga, name='actualizar_liga'),
    path('partido/<int:partido_id>/comparacion/', views.comparacion_equipos, name='comparacion_equipos'),
    path('reporte-pronosticos-pdf/', views.reporte_pronosticos_pdf, name='reporte_pronosticos_pdf'),
    path('enviar-reporte-whatsapp/', views.enviar_reporte_whatsapp, name='enviar_reporte_whatsapp'),
    path('api/partidos-en-vivo/', views.partidos_en_vivo_api, name='partidos_en_vivo_api'),
    path('api/liga/<int:liga_id>/partidos-en-juego/', views.partidos_en_juego_api, name='partidos_en_juego_api'),
]
