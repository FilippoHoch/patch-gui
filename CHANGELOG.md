# Changelog

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file.
Il formato segue le convenzioni di [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il progetto aderisce al [Versionamento Semantico](https://semver.org/lang/it/).

## [Non rilasciato]
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
