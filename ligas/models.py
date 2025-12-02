from django.db import models
from django.utils import timezone


class Liga(models.Model):
    """Modelo para almacenar información de ligas de fútbol"""
    CONTINENTE_CHOICES = [
        ('europa', 'Europa'),
        ('america', 'América'),
        ('asia', 'Asia'),
        ('africa', 'África'),
        ('oceania', 'Oceanía'),
    ]
    
    nombre = models.CharField(max_length=200)
    url = models.URLField(unique=True)
    pais = models.CharField(max_length=100, blank=True)
    continente = models.CharField(max_length=20, choices=CONTINENTE_CHOICES, default='europa')
    codigo_liga = models.CharField(max_length=50, blank=True)
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['continente', 'nombre']
        verbose_name_plural = 'Ligas'
    
    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    """Modelo para equipos de fútbol"""
    liga = models.ForeignKey(Liga, on_delete=models.CASCADE, related_name='equipos')
    nombre = models.CharField(max_length=200)
    
    class Meta:
        ordering = ['nombre']
        unique_together = ['liga', 'nombre']
        verbose_name_plural = 'Equipos'
    
    def __str__(self):
        return f"{self.nombre} ({self.liga.nombre})"


class Partido(models.Model):
    """Modelo para partidos de fútbol"""
    ESTADO_CHOICES = [
        ('programado', 'Programado'),
        ('en_juego', 'En Juego'),
        ('finalizado', 'Finalizado'),
        ('suspendido', 'Suspendido'),
    ]
    
    liga = models.ForeignKey(Liga, on_delete=models.CASCADE, related_name='partidos')
    jornada = models.IntegerField()
    equipo_local = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='partidos_local')
    equipo_visitante = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='partidos_visitante')
    goles_local = models.IntegerField(null=True, blank=True)
    goles_visitante = models.IntegerField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='programado')
    fecha = models.DateField(null=True, blank=True)
    hora = models.TimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    # Campos para rastrear pronóstico 1X2
    pronostico_1x2 = models.CharField(max_length=20, blank=True, null=True)  # 'local', 'empate', 'visitante'
    pronostico_1x2_acertado = models.BooleanField(null=True, blank=True)  # True/False/None
    
    class Meta:
        ordering = ['jornada', 'fecha', 'hora']
        unique_together = ['liga', 'jornada', 'equipo_local', 'equipo_visitante']
        verbose_name_plural = 'Partidos'
    
    def __str__(self):
        if self.goles_local is not None and self.goles_visitante is not None:
            return f"{self.equipo_local.nombre} {self.goles_local}-{self.goles_visitante} {self.equipo_visitante.nombre}"
        return f"{self.equipo_local.nombre} vs {self.equipo_visitante.nombre}"
