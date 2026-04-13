# fga_data_sync/adapters.py
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from fga_data_sync.structs import FGAModelConfig


class FGATupleAdapter:
    """
    Adapter responsible for translating Django model state into OpenFGA tuples.
    Isolated from database signals and HTTP requests for pure unit testing.
    """

    @staticmethod
    def generate_tuples(obj: Any, config: FGAModelConfig) -> list[dict[str, str]]:
        """
        Generates standard OpenFGA tuples based on the model's FGA configuration.

        Args:
            obj: The Django model instance.
            config: The strict dataclass defining the model's OpenFGA mapping.

        Returns:
            list[dict[str, str]]: A list of dictionaries representing Zanzibar tuples.

        Raises:
            ImproperlyConfigured: If config is invalid.
        """
        if not isinstance(config, FGAModelConfig):
            raise ImproperlyConfigured(
                f"Object {obj.__class__.__name__} provided an invalid `fga_config`."
            )

        # Defensive return if the object hasn't been saved yet (no PK)
        if not obj.pk:
            return []

        object_string = f"{config.object_type}:{obj.pk}"
        tuples: list[dict[str, str]] = []

        for parent in config.parents:
            parent_id = getattr(obj, parent.local_field, None)
            if parent_id:
                tuples.append(
                    {
                        "user": f"{parent.parent_type}:{parent_id}",
                        "relation": parent.relation,
                        "object": object_string,
                    }
                )

        for creator in config.creators:
            user_id = getattr(obj, creator.local_field, None)
            if user_id:
                tuples.append(
                    {
                        "user": f"{creator.user_type}:{user_id}",
                        "relation": creator.relation,
                        "object": object_string,
                    }
                )

        return tuples

    @staticmethod
    def compute_diffs(
        old_tuples: list[dict[str, str]], new_tuples: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """
        Computes the delta between two tuple states.

        Args:
            old_tuples: List of tuples before the change.
            new_tuples: List of tuples after the change.

        Returns:
            tuple[list[dict[str, str]], list[dict[str, str]]]: (to_delete, to_write)
        """

        def to_key(t: dict[str, str]) -> str:
            return f"{t['user']}::{t['relation']}::{t['object']}"

        old_set = {to_key(t) for t in old_tuples}
        new_set = {to_key(t) for t in new_tuples}

        tuples_to_delete = [t for t in old_tuples if to_key(t) not in new_set]
        tuples_to_write = [t for t in new_tuples if to_key(t) not in old_set]

        return tuples_to_delete, tuples_to_write
