# Bases de datos de prueba (SQLite)

Este proyecto incluye datasets de ejemplo para Netflix y Uber. Los archivos SQLite (`*.db`) **no se versionan / no se suben al repositorio** porque están ignorados en `.gitignore`.

Para usar la opción **“Usar base de prueba Netflix”** debes generar `frontend/test_data/netflix.db` en tu máquina.

## ✅ Nombre y ubicación esperados

Para que la app encuentre la base de prueba **debes mantener exactamente**:

- **Nombre del archivo:** `netflix.db`
- **Ubicación:** `frontend/test_data/netflix.db`

La aplicación carga esta base automáticamente cuando eliges una de las opciones de muestra en la pantalla de **Nuevo chat**.

---

## Uber Ride Analytics

El archivo `ncr_ride_bookings.csv` contiene 150,000 registros de viajes de 2024. La base se genera como `uber_ride_bookings.db` y contiene la tabla `uber_ride_bookings` con tipos numéricos para importes, distancias, tiempos y calificaciones. Los valores `null` del CSV se convierten en `NULL` de SQLite.

Para generar o regenerar la base:

```bash
cd frontend/test_data
sqlite3 uber_ride_bookings.db < build_uber_ride_bookings.sql
```

El script importa el CSV en una tabla temporal, crea la tabla tipada y agrega índices para las consultas más habituales.

La tabla conserva las 150,000 filas originales. `booking_id` no es único en el archivo fuente, por lo que `row_id` es la clave primaria interna.

## ▶️ ¿Qué pasa si no existe?

Si eliminas o renombras el archivo, el backend mostrará un error indicando que la base de prueba no está disponible.

---

## ✅ ¿Necesito crearla manualmente?

Sí — al menos **una vez** (o cada vez que borres el archivo).

La buena noticia: como `*.db` está ignorado, puedes mantener `netflix.db` en tu máquina sin riesgo de subirlo por accidente.

Para crearla/regenerarla desde cero, usa las instrucciones siguientes.

---

## 🧱 Crear la estructura e importar datos

### 1) Crea la base (si no existe)

```bash
sqlite3 netflix.db
```

### 2) Crea la tabla

```sql
CREATE TABLE netflix_titles (
    show_id TEXT PRIMARY KEY,
    type TEXT,
    title TEXT,
    director TEXT,
    "cast" TEXT,
    country TEXT,
    date_added TEXT,
    release_year INTEGER,
    rating TEXT,
    duration TEXT,
    listed_in TEXT,
    description TEXT
);
```

### 3) Importa el CSV

```sql
.mode csv
.import netflix_titles.csv netflix_titles
```

Asegúrate de ejecutar estos comandos desde la carpeta `frontend/test_data/` para que los archivos queden exactamente en:

```
frontend/test_data/netflix.db
frontend/test_data/netflix_titles.csv
```

---

## ℹ️ Nota importante

Esta base de prueba se usa **solo durante la sesión actual** del servidor. Si reinicias el backend, deberás volver a crear el chat de prueba para usarla de nuevo.
