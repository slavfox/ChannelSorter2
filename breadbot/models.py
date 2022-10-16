# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from tortoise import fields
from tortoise.models import Model


class Guild(Model):
    id = fields.BigIntField(pk=True)
    log_channel_id = fields.BigIntField(null=True)
    archive_category_id = fields.BigIntField(null=True)
    archive_channel_id = fields.BigIntField(null=True)
    channel_owner_role_id = fields.BigIntField(null=True)

    def __str__(self):
        return f"Guild {self.id}"


class ProjectCategory(Model):
    id = fields.BigIntField(pk=True)
    guild = fields.ForeignKeyField(
        "models.Guild", related_name="project_categories"
    )  # type: ignore

    def __str__(self):
        return f"ProjectCategory {self.id}"


class ProjectChannel(Model):
    id = fields.BigIntField(pk=True)
    guild = fields.ForeignKeyField(
        "models.Guild", related_name="project_channels"
    )  # type: ignore
    owner_role = fields.BigIntField()

    def __str__(self):
        return f"ProjectChannel {self.id}"


class AutoThreadChannel(Model):
    id = fields.BigIntField(pk=True)
    guild = fields.ForeignKeyField(
        "models.Guild", related_name="auto_thread_channels"
    )  # type: ignore

    def __str__(self):
        return f"AutoThreadChannel {self.id}"
