# Changelog

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file.
Il formato segue le convenzioni di [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il progetto aderisce al [Versionamento Semantico](https://semver.org/lang/it/).

## [Non rilasciato]
### Aggiunto
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
### Modificato
- La configurazione persistente include ora le impostazioni dedicate
  all'assistente AI ed è documentata nella guida d'uso.

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
