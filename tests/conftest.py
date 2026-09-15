import pytest


@pytest.fixture(autouse=True)
def isolate_publication_state_between_tests():
    """Prevent the process-global in-memory delivery store leaking across tests."""
    from core.publication_engine import reset_local_idempotency_state

    reset_local_idempotency_state()
    yield
    reset_local_idempotency_state()


@pytest.fixture(autouse=True)
def isolate_translation_provider_cooldowns_between_tests():
    """Prevent process-global provider cooldown state leaking across tests."""
    from core.translation_provider_chain import clear_provider_cooldown

    clear_provider_cooldown()
    yield
    clear_provider_cooldown()

