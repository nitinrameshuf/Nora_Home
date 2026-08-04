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
    nora_minimum_role = "admin"
    # No urls.py — this app exists only to hold registry metadata for Mongo/
    # object storage/backups. Its old url_prefix ("home/system/") wasn't a
    # page of its own at all; it just happened to alias the real Status
    # page's URL, which read as a second, fake "Data" app on the directory.
    nora_has_page = False
