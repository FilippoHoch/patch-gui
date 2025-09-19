# Changelog

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file.
Il formato segue le convenzioni di [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il progetto aderisce al [Versionamento Semantico](https://semver.org/lang/it/).

## [Non rilasciato]
### Aggiunto
- Modulo `ai_conflict_helper` per generare suggerimenti testuali e diff
  copiabili quando un hunk non può essere applicato automaticamente; i messaggi
  vengono mostrati nella CLI, nei dialoghi GUI e inclusi nei report di
  sessione.
- Modulo `ai_candidate_selector` con supporto all'invio del contesto a un modello
  AI e recupero del suggerimento migliore per gli hunk ambigui, incluso fallback
  locale se l'endpoint non risponde.
- Opzioni CLI `--ai-assistant` / `--no-ai-assistant` e `--ai-select` per
  controllare l'assistente e applicare automaticamente il suggerimento.
- Nuovi controlli nelle preferenze della GUI e nel dialog dei candidati per
  mostrare confidenza, spiegazione e consentire l'applicazione rapida del
  suggerimento AI.
- Note AI contestuali nella vista diff interattiva, abilitate da una nuova
  preferenza e mostrate direttamente nell'elenco e nell'anteprima.
- Generazione opzionale di sintesi AI della sessione con endpoint configurabile,
  integrazione nei report e nella GUI.
- Supporto all'applicazione di patch binarie Git con diagnostica dedicata e
  integrazione nei flussi CLI/GUI, così da gestire allegati e file compilati
  contenuti nei diff.【F:patch_gui/binary_patch.py†L22-L120】【F:patch_gui/executor.py†L20-L160】
- Vista diff affiancata, barra di ricerca con cronologia e scorciatoie, oltre a
  strumenti per filtrare o pulire il log direttamente dalla finestra principale
  dell'applicazione.【F:patch_gui/interactive_diff.py†L440-L508】【F:patch_gui/app.py†L1963-L2042】【F:patch_gui/diff_search.py†L1-L104】
- Gestore temi centralizzato con palette dinamiche (scuro, chiaro, alto
  contrasto) e aggiornamento live dei widget Qt collegati.【F:patch_gui/theme.py†L31-L156】【F:patch_gui/theme.py†L640-L710】
- Comando `patch-gui restore` per ripristinare i file salvati nei backup,
  utilizzabile anche in modalità non interattiva e con dry-run.【F:patch_gui/cli.py†L310-L384】【F:patch_gui/cli.py†L364-L418】
- Indicizzatore del progetto e nuove strategie di matching che sfruttano
  RapidFuzz e ancore strutturali per trovare più rapidamente le posizioni
  applicabili.【F:patch_gui/file_index.py†L1-L160】【F:patch_gui/matching.py†L160-L240】【F:patch_gui/patcher.py†L120-L188】
- Script dedicati per automatizzare il rilascio e generare i pacchetti
  distribuiti (sdist/wheel) con opzioni di pulizia e verifica.【F:scripts/release_automation.py†L1-L90】【F:scripts/build_packages.py†L1-L84】

### Modificato
- La configurazione persistente include ora le impostazioni dedicate
  all'assistente AI, al tema dell'interfaccia, alla strategia di matching e alle
  ancore strutturali, ed è documentata nella guida d'uso.【F:patch_gui/config.py†L31-L139】
- I report JSON/txt e i log includono i suggerimenti generati dal nuovo
  assistente, mentre CLI e GUI li evidenziano in fase di risoluzione manuale.
- Migliorati gli algoritmi di ricerca dei candidati con RapidFuzz, caching
  dell'indice dei file e nuove opzioni CLI/GUI per controllare strategia,
  ancore e formati dei report.【F:patch_gui/matching.py†L160-L240】【F:patch_gui/file_index.py†L1-L160】【F:patch_gui/patcher.py†L413-L437】【F:patch_gui/parser.py†L120-L207】
- Lo script di automazione del rilascio consente ora di personalizzare remote,
  pruning e modalità dry-run, semplificando il flusso di pubblicazione.【F:scripts/release_automation.py†L1-L90】

### Risolto
- Normalizzazione delle intestazioni `***`/`---` nei diff legacy senza riga di
  destinazione, così da accettarli anche quando mancano i prefissi standard.【F:patch_gui/utils.py†L247-L317】
- Gestione esplicita degli errori HTTP/URL durante il download dell'eseguibile
  Windows con messaggi più chiari per l'utente.【F:patch_gui/downloader.py†L52-L146】

## [0.2.0] - 2025-09-18
### Aggiunto
- Sottocomando `patch-gui download-exe` per scaricare rapidamente l'eseguibile
  Windows pubblicato nelle release ufficiali.
- Opzione CLI `--auto-accept` per applicare automaticamente il candidato migliore
  quando sarebbe richiesto un intervento manuale.
- Parametri di log e conservazione backup configurabili sia dalla GUI sia da
  riga di comando tramite `patch-gui config`.

### Modificato
- Migliorata l'interfaccia del diff interattivo con intestazioni e indicatori
  coerenti tra lista file, hunk e anteprima.
- Documentazione aggiornata (README, guida CLI) con flussi di installazione,
  uso e report più lineari.

## [0.1.0] - 2025-09-18
### Aggiunto
- Prima versione pubblica dell'applicazione `patch-gui`.
