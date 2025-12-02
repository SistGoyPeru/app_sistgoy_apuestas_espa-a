# Sistema de Apuestas Deportivas

Sistema web de análisis y pronósticos deportivos desarrollado con Django.

## Características

- **Dashboard en tiempo real**: Visualización de estadísticas generales y partidos en vivo
- **Análisis multifactorial**: Sistema de pronósticos basado en:
  - Promedio de puntos (40%)
  - Forma reciente (30%)
  - Diferencia de goles (20%)
  - Porcentaje de victorias (10%)
  - Factor localía
- **Comparación de equipos**: Análisis detallado entre dos equipos con:
  - Estadísticas completas (victorias, empates, derrotas, goles)
  - Últimos 5 partidos
  - Pronósticos sobre múltiples mercados (1X2, Over/Under, BTTS, etc.)
- **Verificación de precisión**: Sistema de validación automática de pronósticos
- **Reportes PDF**: Generación de reportes de pronósticos por rango de fechas
- **Gestión de ligas**: CRUD completo para administración de ligas y equipos

## Tecnologías

- **Backend**: Django 5.0
- **Base de datos**: SQLite
- **Frontend**: HTML, CSS, JavaScript (vanilla)
- **API**: API REST para datos en tiempo real

## Instalación

1. Clonar el repositorio:
```bash
git clone [URL_DEL_REPOSITORIO]
cd ApuestasDeportivas
```

2. Crear entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Ejecutar migraciones:
```bash
python manage.py migrate
```

5. Crear superusuario:
```bash
python manage.py createsuperuser
```

6. Ejecutar servidor:
```bash
python manage.py runserver
```

El sistema estará disponible en `http://127.0.0.1:8000/`

## Estructura del Proyecto

```
ApuestasDeportivas/
├── apuestas_deportivas/   # Configuración del proyecto
├── ligas/                 # App principal
│   ├── models.py         # Modelos (Liga, Equipo, Partido)
│   ├── views.py          # Vistas y lógica de negocio
│   ├── templates/        # Plantillas HTML
│   └── static/           # Archivos estáticos
├── media/                # Archivos multimedia
└── manage.py            # Script de administración Django
```

## Scripts de Actualización

- `extraer_data.py`: Script principal para extracción de datos de ligas y partidos

## Uso

### Dashboard
Accede a `/` para ver el dashboard principal con:
- Estadísticas generales del sistema
- Estadísticas por continente
- Partidos en vivo
- TOP 10 mejores pronósticos

### Análisis de Partido
Accede a `/partido/<id>/comparacion/` para ver:
- Comparación detallada entre equipos
- Estadísticas históricas
- Pronósticos para múltiples mercados de apuestas

### Administración
Accede a `/admin/` con las credenciales de superusuario para:
- Gestionar ligas, equipos y partidos
- Configurar parámetros del sistema

## Licencia

Proyecto privado - Todos los derechos reservados
