# Test end-to-end

Test Playwright del percorso demo (storia D4). Girano sullo stack avviato con `make e2e`, nel container `e2e` definito in `compose.override.yaml`.

Ogni test va marcato `@pytest.mark.e2e`. Gli indirizzi dei servizi arrivano dalle variabili `E2E_ASSISTANT_URL`, `E2E_DASHBOARD_URL` ed `E2E_MAILPIT_URL`.
