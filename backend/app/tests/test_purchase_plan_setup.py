"""The additive deployment must preserve an existing external migration marker."""
from sqlalchemy import Column, MetaData, String, Table, Uuid, create_engine, inspect, text

from app.db.setup_purchase_plan import deploy


def test_purchase_proposal_setup_is_explicit_idempotent_and_preserves_external_history():
    engine = create_engine('sqlite://')
    metadata = MetaData()
    for name in ('planning_versions', 'consumables', 'units', 'users'):
        Table(name, metadata, Column('id', Uuid, primary_key=True))
    Table('alembic_version', metadata, Column('version_num', String(32), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO alembic_version VALUES ('external_reviewed_checkpoint')"))
        assert deploy(connection) == {'ready': False, 'created': False,
            'revisions_preserved': ['external_reviewed_checkpoint']}
        assert not inspect(connection).has_table('purchase_plan_drafts')
        assert deploy(connection, apply=True)['created'] is True
        assert {key['referred_table'] for key in inspect(connection).get_foreign_keys('purchase_plan_drafts')} == {
            'planning_versions', 'consumables', 'units', 'users'}
        assert len(inspect(connection).get_unique_constraints('purchase_plan_drafts')) == 1
        assert deploy(connection, apply=True)['created'] is False
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'external_reviewed_checkpoint'
        assert connection.scalar(text('SELECT count(*) FROM purchase_plan_drafts')) == 0
    engine.dispose()
