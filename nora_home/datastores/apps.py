from nora_home.core.registry import Category, NoraAppConfig


class DatastoresConfig(NoraAppConfig):
    name = "nora_home.datastores"
    label = "datastores"
    verbose_name = "Data"

    nora_slug = "data"
    nora_title = "Data"
    nora_description = "MongoDB, object storage, backups, and migration."
    nora_icon = "database"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_order = 50
    nora_url_prefix = "home/system/"
    nora_minimum_role = "admin"
