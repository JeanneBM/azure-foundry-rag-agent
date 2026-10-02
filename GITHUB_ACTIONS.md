# GitHub Actions: walidacja i wdrożenie przez OIDC

Workflow `.github/workflows/ci.yml` wykonuje walidację na push/PR do `main`. Wdrożenie jest ręczne: Actions → Validate and deploy Foundry RAG → Run workflow → branch `main` → zaznacz `deploy`.

## Konfiguracja jednorazowa

1. Utwórz App Registration i Service Principal w Microsoft Entra ID dla tego repozytorium.
2. Dodaj federated credential z:
   - issuer: `https://token.actions.githubusercontent.com`
   - subject: `repo:JeanneBM/jb_classic-rag-foundry:environment:production`
   - audience: `api://AzureADTokenExchange`
3. Nadaj principalowi uprawnienia do zarządzania agentami i wywołania modelu w docelowym Foundry, zgodnie z RBAC organizacji. CI nie tworzy resource group ani usług, więc nie wymaga szerokiej roli Contributor do provisioningu.
4. Skonfiguruj dostęp RemoteTool Connection do Search osobno. Tożsamość CI i tożsamość połączenia agenta to dwie różne ścieżki uwierzytelniania.
5. Utwórz GitHub Environment `production`, dopuść branch `main` i ustaw wymaganych recenzentów, jeśli wymaga tego proces organizacji.
6. Dodaj poniższe secrets i variables w tym środowisku. Nie dodawaj client secret — używany jest OIDC.

| GitHub Environment secrets | Wartość |
|---|---|
| `AZURE_CLIENT_ID` | Client ID App Registration |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |

| GitHub Environment variables | Wartość |
|---|---|
| `PROJECT_ENDPOINT` | Endpoint docelowego projektu Foundry |
| `RAG_MCP_ENDPOINT` | Pełny endpoint istniejącej KB |
| `PROJECT_CONNECTION_NAME` | Nazwa RemoteTool Connection |
| `AGENT_NAME` | Opcjonalnie; domyślnie RagAgent |
| `MODEL_DEPLOYMENT` | Opcjonalnie; domyślnie gpt-4.1-mini |
| `SMOKE_KNOWN_QUESTION` | Pytanie ze znaną odpowiedzią w KB |
| `SMOKE_EXPECTED_SUBSTRING` | Niepusty fragment oczekiwanej odpowiedzi |
| `SMOKE_UNKNOWN_QUESTION` | Pytanie, na które KB nie ma odpowiedzi |

Pytania testowe w variables powinny być odpowiednie do przechowywania w konfiguracji GitHub. Skrypt nie wypisuje odpowiedzi ani dokumentów do logu deploymentu.

Dla private endpoints zmień runner `ubuntu-latest` na runner z dostępem do sieci Foundry. Dostęp Foundry → Search musi działać niezależnie od runnera.

## Co dzieje się podczas wdrożenia

- Najpierw przechodzą lint, formatowanie, testy offline i `pip check`.
- Job wdrożenia uzyskuje OIDC token dopiero po spełnieniu reguł Environment.
- Wymagane zmienne są sprawdzane przed tworzeniem agenta.
- Instalowany jest runtime z wersjami i hashami z `requirements.txt`.
- Skrypt tworzy lub ponownie wykorzystuje wersję kandydata.
- Dwa testy na rzeczywistej KB sprawdzają odpowiedź ze źródłami i przypadek braku wiedzy.
- Dopiero po sukcesie zapisywany jest artifact `foundry-rag-release-<commit SHA>` z `deployment.json`, przechowywany przez 90 dni.

Joby deploymentu są wykonywane kolejno; nowy deployment nie przerywa już uruchomionego. Nie ma automatycznego wdrożenia na push ani kasowania wersji po nieudanym teście.

## Promocja i rollback klienta

Pobierz manifest z udanego runu. Ustaw jego `agent_version` jako `AGENT_VERSION` w środowisku klientów albo dostarcz manifest do klienta z pasującymi endpointem i nazwą agenta. Zachowaj poprzedni manifest poza tymczasowym runnerem. Artifact GitHub nie zastępuje trwałego rejestru wydań.

Wdrożenie tworzy zasób agenta w Foundry; **nie aktualizuje automatycznie środowisk klientów**. Rollback to przełączenie klienta na poprzednią sprawdzoną wersję. Pozostałe wersje pozostają w Azure.

Niepowodzenie smoke testu blokuje zapis verified artifact. Kandydat może już istnieć w Azure i być `latest`, dlatego produkcyjne integracje muszą być przypięte do wersji. Po błędzie provisioning requestu sprawdź stan w Azure przed ręcznym powtórzeniem.

## Sprawdzenie lokalne

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip check
ruff check .
ruff format --check .
python -m pytest -q
```

Instrukcje usług: [Azure login przez OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect), [Foundry RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry).
