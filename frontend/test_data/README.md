# Base de datos de prueba (SQLite)

Este proyecto incluye una base de datos SQLite de ejemplo para probar EzQL sin subir datos propios.

## ✅ Nombre y ubicación esperados

Para que la app encuentre la base de prueba **debes mantener exactamente**:

- **Nombre del archivo:** `netflix.db`
- **Ubicación:** `frontend/test_data/netflix.db`

La aplicación carga esta base automáticamente cuando eliges **“Usar base de prueba Netflix”** en la pantalla de **Nuevo chat**.

---

## ▶️ ¿Qué pasa si no existe?

Si eliminas o renombras el archivo, el backend mostrará un error indicando que la base de prueba no está disponible.

---

## ✅ ¿Necesito crearla manualmente?

No. La base ya viene incluida en el repositorio.

Solo asegúrate de **no cambiarle el nombre ni la ruta**.

Si necesitas regenerarla desde cero, usa las instrucciones siguientes.

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
