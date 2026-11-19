"""Disparadores que impiden UPDATE, DELETE y TRUNCATE sobre la bitácora.

Es la segunda barrera: el modelo ya los rechaza, pero esto vale también contra
SQL directo, una consola o un bug. No protege de quien sea dueño de la tabla y
pueda quitar el disparador; para eso hace falta que el rol de la aplicación solo
tenga INSERT y SELECT (ver docs/DESVIACIONES.md, D-03).
"""

from django.db import migrations

POSTGRES_ADELANTE = """
CREATE FUNCTION auditoria_bitacora_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La bitacora es de solo insercion';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER bitacora_sin_cambios BEFORE UPDATE OR DELETE ON auditoria_bitacora
    FOR EACH ROW EXECUTE FUNCTION auditoria_bitacora_inmutable();
CREATE TRIGGER bitacora_sin_truncate BEFORE TRUNCATE ON auditoria_bitacora
    FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bitacora_inmutable();
"""
POSTGRES_ATRAS = """
DROP TRIGGER bitacora_sin_truncate ON auditoria_bitacora;
DROP TRIGGER bitacora_sin_cambios ON auditoria_bitacora;
DROP FUNCTION auditoria_bitacora_inmutable();
"""
SQLITE_ADELANTE = """
CREATE TRIGGER bitacora_sin_update BEFORE UPDATE ON auditoria_bitacora
BEGIN SELECT RAISE(ABORT, 'La bitacora es de solo insercion'); END;
CREATE TRIGGER bitacora_sin_delete BEFORE DELETE ON auditoria_bitacora
BEGIN SELECT RAISE(ABORT, 'La bitacora es de solo insercion'); END;
"""
SQLITE_ATRAS = """
DROP TRIGGER bitacora_sin_delete;
DROP TRIGGER bitacora_sin_update;
"""


def adelante(apps, schema_editor):
    sql = {"postgresql": POSTGRES_ADELANTE, "sqlite": SQLITE_ADELANTE}.get(schema_editor.connection.vendor)
    if sql is None:
        raise RuntimeError("Motor no soportado: la bitácora exige disparadores de solo inserción.")
    schema_editor.connection.cursor().executescript(sql) if schema_editor.connection.vendor == "sqlite" \
        else schema_editor.execute(sql)


def atras(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.connection.cursor().executescript(SQLITE_ATRAS)
    else:
        schema_editor.execute(POSTGRES_ATRAS)


class Migration(migrations.Migration):
    dependencies = [("auditoria", "0001_initial")]
    operations = [migrations.RunPython(adelante, atras)]
