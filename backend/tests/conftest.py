import pytest

from ringsentinel.config import SimulationConfig
from ringsentinel.simulator.generate import generate


@pytest.fixture(scope="session")
def small_dataset():
    """A small population; enough structure to exercise every code path."""
    return generate(SimulationConfig(n_legit_accounts=1200, n_rings=12, seed=7))
