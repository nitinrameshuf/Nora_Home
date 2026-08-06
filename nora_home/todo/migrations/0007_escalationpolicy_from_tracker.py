"""
Story 40: `EscalationPolicy` moves from the deleted tracker app to Todo.

**This migration changes no state.** `0001_initial` was edited to create
`todo.EscalationPolicy` and to point `Task.escalation_policy` at it, so a
database built from the migrations today already has exactly the right schema
and this file does nothing at all. It exists only for databases that ran the
*original* `0001_initial` — the house's MySQL, and any dev SQLite older than
this commit — where the table is called `tracker_escalationpolicy` and
`todo_task`'s foreign key still points at it.

The convergence is one `RENAME TABLE`, deliberately, rather than
create-copy-repoint-drop. Renaming carries the rows, their primary keys, and
their indexes across untouched, and — on both MySQL and SQLite — automatically
rewrites the foreign keys in *referencing* tables to follow the new name. So
`todo_task`'s constraint ends up pointing at `todo_escalationpolicy` without
anyone having to drop and recreate it, which is the step that would otherwise
have needed vendor-specific SQL and a lookup of MySQL's auto-generated
constraint name.

The one cosmetic residue: on an already-migrated database the carried-over
constraint and index names still read `..._fk_tracker_e`. Django looks
constraints up by the columns they cover, never by name, so this affects nothing
but a `SHOW CREATE TABLE`.
"""

from django.db import migrations

# Children first — each of these is referenced by the one above it.
TRACKER_TABLES = [
    "tracker_escalationevent_notified",
    "tracker_escalationevent",
    "tracker_completion",
    "tracker_occurrence",
    "tracker_trackable",
]


def adopt_the_tracker_policy_table(apps, schema_editor):
    connection = schema_editor.connection
    tables = set(connection.introspection.table_names())

    if "todo_escalationpolicy" in tables:
        # Built from today's 0001. Nothing to converge.
        return

    with connection.cursor() as cursor:
        for table in TRACKER_TABLES:
            if table in tables:
                cursor.execute(f"DROP TABLE {connection.ops.quote_name(table)}")

        if "tracker_escalationpolicy" in tables:
            cursor.execute(
                f"ALTER TABLE {connection.ops.quote_name('tracker_escalationpolicy')} "
                f"RENAME TO {connection.ops.quote_name('todo_escalationpolicy')}"
            )
        else:
            # Neither table exists: a database that somehow has todo's tables
            # but never had the tracker's. Build the table from scratch so the
            # schema still matches the state 0001 declares.
            schema_editor.create_model(apps.get_model("todo", "EscalationPolicy"))

        # The tracker app is gone, so these rows describe migrations no
        # installed app can supply. Django ignores orphans, but leaving them
        # would misreport what this database has actually had applied.
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["tracker"])


class Migration(migrations.Migration):

    dependencies = [
        ("todo", "0006_task_origin_ref"),
    ]

    operations = [
        # No reverse: un-deleting the tracker's tables is not something this
        # project intends to be able to do, and pretending otherwise would be
        # worse than saying so.
        migrations.RunPython(adopt_the_tracker_policy_table, migrations.RunPython.noop),
    ]
