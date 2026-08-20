# JarvisDegen ($JDEGEN)

Socle du MVP d'un agent IA de trading transparent sur Solana. Cette version est exclusivement une simulation locale : elle ne se connecte à aucun wallet et ne peut envoyer aucune transaction.

## État final du MVP

Le cycle de construction en six points est terminé. Le produit est techniquement prêt pour
une revue humaine, mais **aucune stratégie n'est promue** : le dernier contrôle réel valide
2 barrières sur 11, aucun des marchés disponibles n'est rentable sous coûts extrêmes et le
paper automatique supervisé reste désarmé. C'est un résultat de sécurité attendu, pas une panne.

Le trading réel est structurellement impossible : aucun wallet, aucune clé privée, aucun SDK
de signature et aucun appel d'envoi de transaction ne sont présents.

## Fonctionnalités réalisées

- architecture TypeScript initialisée ;
- configuration documentée dans `.env.example` ;
- verrou de simulation obligatoire ;
- moteur de risque déterministe ;
- journal d'audit JSONL ;
- tests des principaux garde-fous.
- vitrine interactive avec concept, tokenomics et feuille de route.
- données publiques Solana en lecture seule via DEX Screener et le RPC mainnet.
- stratégie explicable BUY / SELL / WAIT avec détail des contributions au score.
- backtest sur bougies OHLCV réelles avec frais, slippage, P&L et drawdown.
- comparaison équitable de trois variantes de stratégie et d'un benchmark buy & hold.
- validation hors échantillon avec séparation temporelle 70 % entraînement / 30 % test.
- journal SQLite persistant avec chaînage SHA-256 et exports CSV/JSON.
- brouillons X et Telegram factuels, reliés à l’audit et exportables après validation humaine.
- centre de contrôle local avec verdict, preuves et rapport JSON avant revue humaine.
- portefeuille paper trading SQLite avec cash, positions, frais, slippage, valorisation, P&L et historique du capital.
- moniteur de risque avec perte journalière, drawdown, exposition et coupe-circuit automatique.
- scanner multi-marchés classé par signal, confiance et liquidité, sans exécution automatique.
- mémoire SQLite des scans avec confirmation des signaux, tendances et export JSON.
- surveillance automatique optionnelle toutes les 1, 5 ou 15 minutes, sans ordre automatique.
- centre d’alertes exigeant confirmation, confiance et validation des garde-fous.
- soumission humaine des alertes avec contrôle d’âge et reconfirmation du signal.
- niveaux de protection par position : stop −5 %, objectif +10 % et clôture paper manuelle.
- tableau de performance paper avec coûts, drawdown, statistiques de clôture et attribution par marché.
- validation walk-forward sur trois fenêtres futures disjointes avec benchmark constant.
- laboratoires de confirmation, force du signal et participation par le volume ;
- validations 70/30 et walk-forward séparées pour chaque filtre ;
- validation sous coûts extrêmes sur SOL/USDC, JUP/USDC et BONK/USDC avec tolérance aux sources indisponibles ;
- sélection de candidat strictement bloquée lorsque la validation locale ou multi-marchés échoue ;
- politique de paper trading supervisé avec approbation humaine par ordre ;
- surveillance de dérive paper/backtest à partir de dix trades clôturés ;
- certificat final et audit de sécurité reproductible.

## Démarrage

Prérequis : Node.js 20 ou supérieur.

```bash
npm install
npm run check
npm run dev
```

Le scénario de démonstration utilise un signal entièrement fictif et écrit son résultat dans `logs/simulations.jsonl`.

## Interface visuelle

Sous PowerShell :

```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

Ouvrir ensuite `http://localhost:8501`. Le bouton de simulation alimente un journal distinct dans `logs/dashboard_simulations.jsonl`.

## Configuration

Copier `.env.example` vers `.env` uniquement lorsque le chargement d'environnement sera ajouté. Pour l'instant, les valeurs par défaut sécurisées sont intégrées au prototype. Ne jamais ajouter de seed phrase ou de clé privée au projet.

## Feuille de route

1. Socle, simulation et gestion du risque - réalisé.
2. Identité visuelle et site vitrine - réalisé dans le prototype local.
3. Sources de données Solana en lecture seule - réalisé.
4. Stratégie explicable, paper trading, backtests et validation hors échantillon - réalisés.
5. Tableau de bord public et preuves auditables - première version réalisée.
6. Communication sociale avec validation humaine initiale - brouillons locaux réalisés.
7. Centre de contrôle, tests prolongés et audit local réalisés. Un audit indépendant externe reste recommandé avant toute évolution du périmètre.

## Verdict de certification du 20 août 2026

- 95 tests Python réussis ;
- 4 tests TypeScript réussis et compilation stricte réussie ;
- audit de lancement : 6/6 contrôles, aucun blocage ;
- chaîne d'audit : 17 décisions vérifiées ;
- validation locale : 2/11 barrières ;
- multi-marchés : 0/2 marchés disponibles positifs sous stress ;
- BONK/USDC indisponible lors du contrôle (aucune paire liquide trouvée) ;
- candidat paper : aucun ;
- paper automatique : désarmé ;
- trading réel : impossible.

Voir [FINAL_AUDIT.md](FINAL_AUDIT.md) pour le compte rendu complet.

Voir `docs/ARCHITECTURE.md` pour les choix techniques et les frontières de sécurité.
