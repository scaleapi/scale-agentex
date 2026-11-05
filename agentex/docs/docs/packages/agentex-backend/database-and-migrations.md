## Backend: database & migrations (`agentex/database/`)

The backend persists relational data in PostgreSQL using SQLAlchemy, with schema migrations managed by Alembic.

### What lives here

- **Alembic config**: `database/migrations/alembic.ini`
- **Alembic environment**: `database/migrations/alembic/env.py`
- **Migration scripts**: `database/migrations/versions/*.py`
- **Migration history export**: `database/migrations/migration_history.txt`

### When you need a migration

Create a migration whenever you change:

- SQLAlchemy models / relational schema
- constraints, indexes, or columns for relational entities

From `agentex/`:

```bash
make migration NAME="describe_change"
make apply-migrations
```

### MongoDB collections

MongoDB is used for document-oriented storage (not managed by Alembic). Index requirements are usually defined in:

- `src/config/mongodb_indexes.py`

