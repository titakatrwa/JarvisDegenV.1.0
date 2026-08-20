# Architecture du MVP JarvisDegen

## Principe directeur

L'étape 1 ne signe et n'envoie aucune transaction. Elle transforme un signal fictif en décision contrôlée, puis conserve une trace locale auditable.

```text
Signal simulé -> Moteur de risque -> Décision simulée -> Journal JSONL
                         |
                         +-> refus si un garde-fou est dépassé
```

## Modules actuels

- `config.ts` : charge les paramètres et impose le mode simulation.
- `risk-engine.ts` : applique les limites sans accès réseau.
- `simulator.ts` : produit une décision et écrit le journal d'audit.
- `index.ts` : scénario de démonstration local.
- `backtest.py` : moteur historique, stress des coûts, filtres et validations chronologiques.
- `lifecycle.py` : robustesse multi-marchés, sélection du candidat, politique paper et dérive.
- `paper_portfolio.py` : portefeuille SQLite exclusivement simulé.
- `backtest_report.py` : rapport compact signé par SHA-256.
- `launch_audit.py` : vérification locale des frontières de sécurité.

## Architecture cible

Les étapes ultérieures ajouteront des adaptateurs isolés : données Solana/Helius, cotations Jupiter, moteur de stratégie, portefeuille de simulation, tableau de bord et publication sociale. L'exécution réelle restera séparée derrière une interface explicite et des validations supplémentaires.

## Frontières de sécurité

- aucune clé privée dans le dépôt ou les variables de l'étape 1 ;
- aucun SDK de transaction installé ;
- démarrage bloqué si `SIMULATION_MODE` n'est pas `true` ;
- taille maximale d'une position : 2 % du capital virtuel ;
- perte journalière maximale : 3 % ;
- trois positions ouvertes au maximum ;
- confiance minimale d'un signal : 70 %.

Ces valeurs sont des hypothèses de prototypage, pas des conseils financiers. Elles devront être testées sur données historiques avant toute évolution.

## Cycle de promotion

```text
Backtest local (11 barrières)
        |
        v
Validation multi-marchés sous coûts extrêmes
        |
        v
Sélection d'un candidat (refus par défaut)
        |
        v
Paper supervisé + approbation humaine par ordre
        |
        v
Moniteur de dérive (minimum 10 trades clôturés)
```

Une absence de candidat désarme la politique paper. Aucun état de ce cycle ne peut activer
le trading réel, car cette capacité n'existe pas dans le code ni dans les dépendances.
