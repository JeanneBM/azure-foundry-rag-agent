# Azure Foundry RAG Agent

Agent RAG na Microsoft Foundry Agent Service, korzystający z Azure AI Search Knowledge Base przez MCP. Repozytorium wdraża **wersję agenta** i dostarcza klienta terminalowego. Bazę wiedzy, indeksy, model i połączenie RemoteTool należy przygotować wcześniej.

Klient wymusza wywołanie `knowledge_base_retrieve` i sprawdza wynik przed pokazaniem odpowiedzi. Odpowiedź merytoryczna musi cytować identyfikatory rzeczywiście zwrócone w bieżącym wyszukiwaniu. Te kontrole potwierdzają pochodzenie źródeł, ale nie dowodzą, że każde zdanie wynika z dokumentów. Jakość retrieval i zgodność odpowiedzi ze źródłami wymagają ewaluacji na danych docelowych.

[English documentation](README_EN.md) · [GitHub Actions i OIDC](GITHUB_ACTIONS.md)

## Wymagania i zakres

- Python **3.12**: blokady zależności i CI są przygotowane dla tej wersji.
- Projekt Foundry z wdrożonym modelem obsługującym Responses API i MCP.
- Azure AI Search z gotową Knowledge Base i zakończonym indeksowaniem.
- Połączenie Foundry typu RemoteTool do dokładnego endpointu MCP.
- Azure CLI do lokalnego logowania i OIDC w CI albo Managed Identity w środowisku Azure.

To jest wdrożenie zarządzanego agenta Foundry i klient CLI. Repo nie tworzy infrastruktury, nie indeksuje dokumentów i nie wystawia publicznego HTTP API. Kontrolę odpowiedzi implementuje klient z tego repo; użycie samego agenta przez innego klienta pomija te kontrole.

## Przygotowanie Azure

1. Przygotuj Knowledge Base z treściami, do których użytkownicy mają mieć dostęp. Sprawdź w portalu, czy retrieval zwraca fragmenty i identyfikatory `ref_id`.
2. Wdróż wybrany model w projekcie Foundry. `MODEL_DEPLOYMENT` jest nazwą **wdrożenia**, nie nazwą katalogową modelu.
3. Utwórz RemoteTool Connection do endpointu Knowledge Base. Dla uwierzytelniania przez Managed Identity ustaw audience `https://search.azure.com/` i nadaj tożsamości używanej przez połączenie rolę **Search Index Data Reader** na usłudze Search. Sprawdź faktyczną tożsamość w konfiguracji połączenia.
4. Tożsamości wdrażającej agenta nadaj uprawnienia do zarządzania agentami projektu i wywoływania modelu, np. **Foundry User** (wcześniej Azure AI User) na właściwym zasobie Foundry, zgodnie z polityką RBAC organizacji. Ogranicz zakres do potrzebnego zasobu.
5. Zapewnij dostęp sieciowy zarówno klient → Foundry, jak i Foundry → Search. Dla prywatnych endpointów użyj odpowiednio podłączonego środowiska i runnera CI.

Wszyscy użytkownicy tego klienta korzystają z uprawnień połączenia do KB. Nie ma tu przekazywania tożsamości użytkownika ani egzekwowania osobnych ACL dokumentów. Baza i jej połączenie muszą być przeznaczone dla wspólnej, uprawnionej grupy odbiorców.

## Instalacja

```bash
git clone https://github.com/JeanneBM/jb_classic-rag-foundry.git
cd jb_classic-rag-foundry
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
python -m pip check
cp .env.example .env
az login
```

Uzupełnij `.env` rzeczywistymi wartościami. Nie zapisuj tokenów ani kluczy w endpointach. Istniejące zmienne procesu mają pierwszeństwo przed `.env`.

| Zmienna | Znaczenie |
|---|---|
| `PROJECT_ENDPOINT` | HTTPS endpoint projektu kończący się `/api/projects/<project>` |
| `RAG_MCP_ENDPOINT` | Dokładny endpoint KB: `/knowledgebases/<kb>/mcp?api-version=...` |
| `PROJECT_CONNECTION_NAME` | Nazwa istniejącego RemoteTool Connection |
| `MODEL_DEPLOYMENT` | Nazwa wdrożenia modelu; domyślnie `gpt-4.1-mini` |
| `AGENT_NAME` | Nazwa agenta; domyślnie `RagAgent` |
| `AGENT_VERSION` | Konkretna, sprawdzona wersja dla klienta; bez wartości odczyt z manifestu |
| `DEPLOYMENT_FILE` | Manifest wersji; domyślnie `deployment.json` |
| `AZURE_CREDENTIAL_MODE` | `default`, `cli` lub `managed_identity` |
| `MANAGED_IDENTITY_CLIENT_ID` | Opcjonalny client ID tożsamości przypisanej przez użytkownika |
| `REQUEST_TIMEOUT_SECONDS` | Timeout pojedynczego żądania; domyślnie 120 s |
| `MAX_OUTPUT_TOKENS` | Limit generowanej odpowiedzi; domyślnie 2048 |
| `MAX_QUESTION_CHARS` | Limit pytania; domyślnie 8000 znaków |
| `HISTORY_TURNS` | Liczba zachowanych par pytanie/odpowiedź; domyślnie 6, 0 wyłącza historię |

Przykład używa GA Search API `2026-04-01`, które zwraca dane extractive. Jeśli konfiguracja KB wymaga innej wersji, użyj endpointu podanego przez Azure. Funkcje preview trzeba ocenić osobno przed wdrożeniem produkcyjnym. Parser obsługuje rekordy grounding z `ref_id` i niepustym `content`, bezpośrednio lub w obudowie MCP `content[].text` / `result.content[].text`. Inny format zostanie odrzucony.

## Utworzenie wersji i sprawdzenie wdrożenia

```bash
python create_rag_agent.py
```

Skrypt porównuje pełną definicję z najnowszą wersją. Jeśli jest identyczna, używa istniejącej wersji. Zmiana definicji tworzy nową, niezmienną wersję. `--force` tworzy nową wersję również bez zmian. Wynik zapisuje atomowo w `deployment.json`.

**Manifest po utworzeniu opisuje kandydata**, dopóki nie przejdzie sprawdzeń na Azure. Użyj dwóch pytań dopasowanych do swojej bazy: jednego ze znaną odpowiedzią i drugiego, na które baza nie odpowiada.

```bash
python smoke_test.py \
  --known-question "Jaki jest termin zwrotu produktu?" \
  --expected-substring "30 dni" \
  --unknown-question "Jaki jest prywatny numer telefonu osoby niewymienionej w dokumentach?"
```

Powyższe pytania są przykładowe. Test wymaga poprawnego retrieval, cytowania i oczekiwanego fragmentu dla pierwszego pytania oraz dokładnego `I don't know` dla drugiego. Błąd kończy program kodem 1; nie jest traktowany jako zaliczony brak wiedzy.

Po sukcesie ustaw `AGENT_VERSION` na numer z manifestu w środowisku klienta. Klient nigdy nie wybiera automatycznie `latest`. Pierwszeństwo: `--version` → `AGENT_VERSION` → manifest zgodny z nazwą agenta i endpointem projektu.

```bash
python chat.py
python chat.py --version 2 --question "Jaki jest termin zwrotu?" --json
```

Klient pokazuje cytowania `[ref_id:X]` i metadane cytowanych źródeł. Nie tworzy zmyślonych URL-i. Brak URL-a w rekordzie oznacza, że klient go nie pokaże.

## Zachowanie przy błędach

- Brak retrieval, błędne MCP, niepełna odpowiedź lub cytowanie spoza bieżących wyników: odpowiedź modelu jest odrzucana.
- Tryb interaktywny pokazuje `I don't know` i osobny diagnostyczny komunikat na stderr. Tryb `--question` zwraca kod 1 i nie emituje niezweryfikowanej odpowiedzi.
- Błędy sieci i RBAC są odróżniane od braku wiedzy. Treści zdalnych błędów, tokeny i fragmenty dokumentów nie są wypisywane w diagnostyce.
- Do lokalnej historii trafiają tylko zaakceptowane odpowiedzi. Każde nowe pytanie ponownie wymaga retrieval.
- Responses API jest wywoływane z `store=False`; klient nie tworzy trwałych Conversations. Polityki retencji i monitoringu usługi Azure należy skonfigurować osobno.
- Wywołania Responses mają maksymalnie dwa ponowienia SDK. Timeout dotyczy pojedynczej próby. Zarządzanie agentami nie ma automatycznych ponowień, aby nie powielać wersji po utracie odpowiedzi. Po timeout podczas tworzenia najpierw sprawdź stan agenta w Azure.

## Rollback i usuwanie

Rollback klienta polega na ustawieniu wcześniejszego, zweryfikowanego `AGENT_VERSION` albo `--version`. Nie usuwa to żadnych wersji w Azure. Zachowaj manifest poprzedniego wydania.

Tworzenie nowej wersji zmienia `latest` w Foundry również przed smoke testem. Wszyscy klienci produkcyjni powinni używać jawnie przypiętej wersji; nazwa agenta bez wersji nie zapewnia izolacji od kandydata.

```bash
python delete_rag_agent.py --version 2 --yes
# Usunięcie agenta i WSZYSTKICH jego wersji:
python delete_rag_agent.py --all --yes
```

Nie ma domyślnej wersji do usunięcia. Usunięcie nie aktualizuje manifestów ani konfiguracji klientów — najpierw przenieś klientów na zachowaną wersję.

## CI/CD i rozwój

Push i PR do `main` uruchamiają lint, formatowanie, testy offline i kontrolę zależności. Ręczne `workflow_dispatch` z `deploy=true` na `main` tworzy kandydata przez OIDC, sprawdza go na prawdziwej KB i zapisuje manifest jako artifact dopiero po sukcesie. Konfiguracja: [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md).

```bash
python -m pip install --require-hashes -r requirements-dev.txt
ruff check .
ruff format --check .
python -m pytest -q
```

Testy offline używają rzeczywistych modeli/serializacji SDK i atrap transportu HTTP. Nie potwierdzają poprawności RBAC, sieci ani zawartości KB — temu służy `smoke_test.py`.

Zależności runtime i dev są rozdzielone oraz zablokowane z hashami. Po świadomej zmianie wersji w plikach `.in` wygeneruj blokady na Pythonie 3.12 i powtórz testy:

```bash
python -m pip install pip-tools==7.6.1
pip-compile --generate-hashes --no-emit-index-url --no-emit-trusted-host -o requirements.txt requirements.in
pip-compile --generate-hashes --no-emit-index-url --no-emit-trusted-host -o requirements-dev.txt requirements-dev.in
```

## Dokumentacja usług

- [Połączenie Foundry z Knowledge Base](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect)
- [Format MCP i wersje Search API](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)
- [AgentReference i Responses API](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject)
- [Runtime i przechowywanie odpowiedzi](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/runtime-components)

## Licencja

MIT
