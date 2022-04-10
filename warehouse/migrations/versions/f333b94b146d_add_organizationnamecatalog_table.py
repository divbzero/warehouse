# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Add OrganizationNameCatalog table

Revision ID: f333b94b146d
Revises: 40e94cf8bf97
Create Date: 2022-04-08 20:21:36.198249
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f333b94b146d"
down_revision = "40e94cf8bf97"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "organization_name_catalog",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name",
            "organization_id",
            name="_organization_name_catalog_name_organization_uc",
        ),
    )
    op.create_index(
        "organization_name_catalog_name_idx",
        "organization_name_catalog",
        ["name"],
        unique=False,
    )
    op.create_index(
        "organization_name_catalog_organization_id_idx",
        "organization_name_catalog",
        ["organization_id"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "organization_name_catalog_organization_id_idx",
        table_name="organization_name_catalog",
    )
    op.drop_index(
        "organization_name_catalog_name_idx", table_name="organization_name_catalog"
    )
    op.drop_table("organization_name_catalog")
    # ### end Alembic commands ###
