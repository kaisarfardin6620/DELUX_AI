# Production Notes

## Database migrations

- The FastAPI app reads Django-owned PostgreSQL tables.
- Run schema migrations from the Django project that owns the models.
- Keep a compatibility check between Django schema changes and this FastAPI reader before deploys.

## Database backups

- Use a scheduled PostgreSQL backup outside the app, for example `pg_dump` from the VPS or your managed database provider.
- Store backups off the server, not only on the same disk.
- Test restores on a staging copy regularly.

Example backup flow:

1. `pg_dump` the PostgreSQL database daily.
2. Compress and upload the dump to external storage.
3. Restore the dump into a staging database monthly to verify it works.

## Media backups

- Uploaded media is stored in the FastAPI project `media/` folder.
- Back up that folder together with the database backups.
- If the media folder is on a Docker volume or VPS disk, include it in your server backup job.
- Test restoring a few sample images after backup.

## Media upload rules

- Only image files are accepted.
- Files are limited by `MEDIA_MAX_UPLOAD_MB`.
- Uploads are protected by JWT access tokens.
