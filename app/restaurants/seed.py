from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.restaurants.models import MenuCategory, MenuItem, Restaurant
from app.restaurants.schemas import RestaurantSeed

SEED_FILE_ADAPTER = TypeAdapter(list[RestaurantSeed])


class CatalogueSeedService:
    @classmethod
    def seed_if_empty(cls, session: Session, seed_file: Path) -> int:
        """Inserts the seed catalogue unless any restaurant exists; returns how many were added.

        Checking for an empty table (not upserting by name) never overwrites admin edits.
        """
        if session.scalar(select(exists().select_from(Restaurant))):
            return 0
        restaurants = SEED_FILE_ADAPTER.validate_json(seed_file.read_bytes())
        session.add_all(cls._build_restaurant(seed) for seed in restaurants)
        session.commit()
        return len(restaurants)

    @staticmethod
    def _build_restaurant(seed: RestaurantSeed) -> Restaurant:
        return Restaurant(
            name=seed.name,
            description=seed.description,
            cuisine=seed.cuisine,
            address=seed.address,
            delivery_fee_cents=seed.delivery_fee_cents,
            categories=[
                MenuCategory(
                    name=category.name,
                    position=position,
                    items=[MenuItem(**item.model_dump()) for item in category.items],
                )
                for position, category in enumerate(seed.categories)
            ],
        )
