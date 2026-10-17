"""Read-only loading measurements. Prints counts and timings, never rows or secrets."""
import json
import time

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.core.config import load_settings
from app.db.session import create_db_engine
from app.models.auth import User
from app.models.masters import Product
from app.api.production import get_routes
from app.repositories.auth import find_user_with_permissions
from app.schemas.production import RouteResponse
from app.services.mappings import (
    list_product_plant_mappings, list_product_process_consumable_mappings,
    resolve_product_mapping, validate_mappings,
)
from app.services.product import list_products


def main():
    engine = create_db_engine(load_settings())
    statements = []
    event.listen(engine, 'before_cursor_execute',
                 lambda connection, cursor, statement, parameters, context, many: statements.append(1))
    try:
        with Session(engine) as session:
            session.execute(text('SET TRANSACTION READ ONLY'))
            user_id = session.scalar(select(User.id).where(User.username == 'admin'))
            product_id = session.scalar(select(Product.id).order_by(Product.code).limit(1))

        def measure(name, operation):
            start = time.monotonic()
            with Session(engine) as session:
                session.execute(text('SET TRANSACTION READ ONLY'))
                statements.clear()
                data_start = time.monotonic()
                result = operation(session)
                data_seconds = time.monotonic() - data_start
                query_count = len(statements)
                size = len(result) if isinstance(result, list) else None
            print(json.dumps({'operation': name, 'seconds': round(time.monotonic() - start, 3),
                              'data_seconds': round(data_seconds, 3),
                              'sql_statements': query_count, 'records': size}), flush=True)

        measure('database_round_trip', lambda s: s.execute(text('SELECT 1')).all())
        if user_id:
            measure('authentication_permissions', lambda s: find_user_with_permissions(s, user_id))
        measure('products', list_products)
        measure('product_plant_mappings', list_product_plant_mappings)
        measure('process_consumable_mappings', list_product_process_consumable_mappings)
        measure('routes_with_steps', lambda s: [RouteResponse.model_validate(route) for route in get_routes(db=s)])
        measure('all_product_validation', validate_mappings)
        if product_id:
            measure('one_product_resolution', lambda s: resolve_product_mapping(s, product_id))
            measure('one_product_validation', lambda s: validate_mappings(s, product_id))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
