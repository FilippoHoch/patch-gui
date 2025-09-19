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
- Generazione opzionale di sintesi AI della sessione con endpoint configurabile,
  integrazione nei report e nella GUI.
### Modificato
- La configurazione persistente include ora le impostazioni dedicate
  all'assistente AI ed è documentata nella guida d'uso.
- I report JSON/txt e i log includono i suggerimenti generati dal nuovo
  assistente, mentre CLI e GUI li evidenziano in fase di risoluzione manuale.

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
