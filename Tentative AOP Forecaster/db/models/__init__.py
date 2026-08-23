"""Import every model module so Base.metadata is complete for Alembic autogenerate."""
from . import masterdata, calendar, planning_inputs, sync, engine, auth, workflow, audit  # noqa: F401
