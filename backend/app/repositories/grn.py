from decimal import Decimal

from sqlalchemy import func, select

from app.models.grn import GRN, GRNItem


def totals(session, item_id):
    row = session.execute(select(func.sum(GRNItem.received_quantity), func.sum(GRNItem.accepted_quantity),
                                 func.sum(GRNItem.rejected_quantity)).where(GRNItem.purchase_order_item_id == item_id)).one()
    return tuple(value if value is not None else Decimal('0') for value in row)


def items(session, identity):
    return session.scalars(select(GRNItem).where(GRNItem.grn_id == identity).order_by(GRNItem.source_line_id)).all()


def by_source(session, source_id):
    return session.scalar(select(GRN).where(GRN.source_grn_id == source_id))
