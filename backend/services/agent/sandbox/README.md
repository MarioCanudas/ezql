# Statistics sandbox image

Build the pinned runtime before deploying the backend:

```sh
docker build -t ezql-statistics-sandbox:0.1.0 backend/services/agent/sandbox
```

The backend never mounts this directory, the database, or any host path into a
running sandbox container.
