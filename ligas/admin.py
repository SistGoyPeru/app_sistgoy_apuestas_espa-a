from django.contrib import admin
from .models import Liga, Equipo, Partido


@admin.register(Liga)
class LigaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'pais', 'activa', 'ultima_actualizacion']
    list_filter = ['activa', 'pais']
    search_fields = ['nombre', 'pais']


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'liga']
    list_filter = ['liga']
    search_fields = ['nombre']


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = ['liga', 'jornada', 'equipo_local', 'goles_local', 'goles_visitante', 'equipo_visitante', 'estado', 'fecha']
    list_filter = ['liga', 'estado', 'jornada']
    search_fields = ['equipo_local__nombre', 'equipo_visitante__nombre']
    date_hierarchy = 'fecha'
