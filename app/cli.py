"""Operational commands: `python -m app.cli <command>`."""

import argparse
import logging
from logging import getLogger
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.restaurants.seed import CatalogueSeedService

SEED_FILE = Path(__file__).resolve().parents[1] / 'seed' / 'restaurants.json'

logger = getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog='python -m app.cli')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed', help='Insert demo restaurants if the catalogue is empty.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s [%(name)s] %(message)s')
    if args.command == 'seed':
        seed()


def seed() -> None:
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            added = CatalogueSeedService.seed_if_empty(session, SEED_FILE)
    finally:
        engine.dispose()
    if added:
        logger.info('Seeded %d restaurants.', added)
    else:
        logger.info('Restaurants already present; seed skipped.')


if __name__ == '__main__':
    main()
