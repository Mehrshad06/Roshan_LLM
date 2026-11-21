"""Give the existing demo administrator access on upgraded installations."""
from django.db import migrations


def grant_catalog_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("auth", "User")
    demo = User.objects.using(alias).filter(username="demo", is_staff=True).first()
    if not demo:
        return
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    catalog, _ = ContentType.objects.using(alias).get_or_create(app_label="library", model="languagemodel")
    for action in ("view", "add", "change", "delete"):
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=catalog, codename=f"{action}_languagemodel",
            defaults={"name": f"Can {action} language model"},
        )
        demo.user_permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("library", "0002_languagemodel_conversation_language_model"),
                    ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(grant_catalog_permissions, migrations.RunPython.noop)]
