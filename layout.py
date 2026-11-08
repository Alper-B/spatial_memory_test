"""
layout.py
---------
Spatial Layout Manager for TMT-A Spatial Memory Experiments.

Implements a fully random 'sprinkled on the floor' layout algorithm:
- Scatter N non-overlapping circular nodes across the board without clustering.
- Numerical identity is decoupled from coordinates via random shuffling (zero sequential proximity bias).
- Dynamic reshuffling for Mode 3 (shuffling only uncompleted targets) and Mode 4 (shuffling all targets).
"""

import math
import random
from typing import Dict, List, Optional, Tuple


class SpatialLayoutManager:
    """
    Handles layout generation using a fully random floor sprinkling algorithm.
    Decouples target numbering from spatial position so sequential numbers
    have zero spatial proximity correlation.
    """

    @staticmethod
    def _compute_default_spacing(count: int) -> float:
        """Dynamically computes minimum spacing between node centers in percentage units."""
        return max(4.0, min(7.5, 36.0 / math.sqrt(max(1, count))))

    @classmethod
    def _place_sprinkled_positions(
        cls,
        count: int,
        existing_positions: List[Tuple[float, float]],
        rng: random.Random,
        min_spacing: Optional[float] = None,
        margin: float = 6.0,
    ) -> List[Tuple[float, float]]:
        """
        Places `count` non-overlapping positions in [margin, 100 - margin] percentage coordinates,
        guaranteeing distance >= spacing from `existing_positions` and from each other.
        """
        total_count = len(existing_positions) + count
        spacing = min_spacing if min_spacing is not None else cls._compute_default_spacing(total_count)
        floor_spacing = max(3.8, spacing * 0.75)

        new_positions: List[Tuple[float, float]] = []
        max_attempts = 4000

        for _ in range(count):
            placed = False
            cur_spacing = spacing

            for attempt in range(max_attempts):
                if attempt > 1400:
                    cur_spacing = max(floor_spacing, cur_spacing * 0.99)

                x = rng.uniform(margin, 100.0 - margin)
                y = rng.uniform(margin, 100.0 - margin)

                # Keep top-left corner clear so targets never collide with the "First Target" corner badge
                if x < 19.0 and y < 21.0:
                    continue

                # Collision check against fixed positions and already placed new positions
                if all(math.hypot(x - ex, y - ey) >= cur_spacing for ex, ey in existing_positions) and \
                   all(math.hypot(x - nx, y - ny) >= cur_spacing for nx, ny in new_positions):
                    new_positions.append((round(x, 2), round(y, 2)))
                    placed = True
                    break

            if not placed:
                # Fallback: place with boundary clamping
                new_positions.append((
                    round(rng.uniform(margin, 100.0 - margin), 2),
                    round(rng.uniform(margin, 100.0 - margin), 2),
                ))

        return new_positions

    @classmethod
    def generate_initial_layout(
        cls,
        targets: List[str],
        seed: Optional[int] = None,
        rng: Optional[random.Random] = None,
        min_spacing: Optional[float] = None,
        margin: float = 6.0,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Generates randomly sprinkled non-overlapping target positions across the board.
        Labels are randomly shuffled onto positions to ensure zero proximity bias.
        """
        if rng is None:
            rng = random.Random(seed)

        positions = cls._place_sprinkled_positions(
            count=len(targets),
            existing_positions=[],
            rng=rng,
            min_spacing=min_spacing,
            margin=margin,
        )

        # Decouple sequence order from coordinates
        rng.shuffle(positions)
        return {target: pos for target, pos in zip(targets, positions)}

    @classmethod
    def shuffle_uncompleted_targets(
        cls,
        current_layout: Dict[str, Tuple[float, float]],
        completed_targets: List[str],
        uncompleted_targets: List[str],
        rng: Optional[random.Random] = None,
        min_spacing: Optional[float] = None,
        margin: float = 6.0,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Mode 3: Preserves the exact positions of completed targets,
        and freely sprinkles all remaining uncompleted targets to new uniformly random positions.
        """
        if rng is None:
            rng = random.Random()

        fixed_positions = [current_layout[t] for t in completed_targets]
        new_positions = cls._place_sprinkled_positions(
            count=len(uncompleted_targets),
            existing_positions=fixed_positions,
            rng=rng,
            min_spacing=min_spacing,
            margin=margin,
        )

        rng.shuffle(new_positions)

        result = {t: current_layout[t] for t in completed_targets}
        for t, pos in zip(uncompleted_targets, new_positions):
            result[t] = pos

        return result

    @classmethod
    def shuffle_all_targets(
        cls,
        targets: List[str],
        rng: Optional[random.Random] = None,
        min_spacing: Optional[float] = None,
        margin: float = 6.0,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Mode 4: Re-sprinkles all targets to brand new random floor positions.
        """
        return cls.generate_initial_layout(
            targets=targets,
            rng=rng,
            min_spacing=min_spacing,
            margin=margin,
        )

