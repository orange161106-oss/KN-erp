"""Recovery must fail closed when the inspected schema has changed."""
import pytest
from sqlalchemy import Boolean, Column, String
from app.db.recover_product_setup import EXTERNAL_COLUMNS, verify_differences
from app.models.auth import User
from app.models.masters import Product


def inspected_differences():
    index = next(i for i in User.__table__.indexes if i.name == 'uq_users_single_super_admin')
    return [
        ('add_column', None, 'products', Product.__table__.c.item_id),
        ('add_column', None, 'products', Product.__table__.c.part_number),
        ('add_index', index),
        *(('remove_column', None, 'users', Column(name, Boolean)) for name in EXTERNAL_COLUMNS),
    ]


def test_recovery_accepts_only_the_inspected_case():
    verify_differences(inspected_differences())


def test_recovery_refuses_unrelated_schema_changes():
    with pytest.raises(RuntimeError):
        verify_differences(inspected_differences() + [('remove_column', None, 'products', Column('name', String))])


def test_recovery_refuses_already_migrated_or_incomplete_case():
    with pytest.raises(RuntimeError):
        verify_differences(inspected_differences()[1:])
