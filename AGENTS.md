<!-- BEGIN MANAGED DEV WORKSPACE POLICY -->

# Politique de travail partagée — /Users/td/Dev

Cette politique s'applique à tous les dépôts canoniques sous `/Users/td/Dev`. Elle prime sur les anciennes règles Git/concurrence incompatibles. Les règles métier propres à chaque dépôt restent prioritaires hors de ce périmètre.

## État local et concurrence

- Le contenu du checkout local canonique est la base de travail. `HEAD` et `origin/*` servent à comparer et publier, jamais à effacer automatiquement un état local.
- Un arbre `dirty` n'est pas une erreur. Ne jamais utiliser `stash`, `restore`, `reset`, `checkout -- <fichier>` ou `clean` pour obtenir artificiellement un arbre propre ou contourner un conflit de session.
- Avant d'éditer, raisonner par chemin, pas par statut global. Lire le fichier courant et son diff éventuel.
- Le délai de reprise dépend du type de fichier, car 2 h universelles bloquent inutilement les workflows courts :
  - `PLAN_*.md` et `docs/plans/README.md` / `plans/README.md` : **30 min** sans activité ;
  - fichier ordinaire : **60 min** sans activité ;
  - fichier à fort rayon d'explosion : **90 min** sans activité. Cette classe couvre au minimum `AGENTS.md`, `policies/dev-workspace.md`, les lockfiles partagés, les manifests/configs structurants listés par `scripts/dev_workspace_lease.py`, les workflows CI et les plists.
- Un délai expiré signifie seulement **« reprise autorisée après préflight »**, jamais « tâche terminée » ni « contenu abandonné ». Conserver les octets locaux présents comme base, relire le diff existant, puis ajouter le changement demandé sans revenir à `HEAD`.
- Exception : le fichier appartient déjà explicitement à la tâche/session courante. Cette propriété doit rester explicite et ne permet pas d'ignorer une modification concurrente observée après le préflight.
- Pour un plan activement travaillé, utiliser de préférence un lease borné : `python3 scripts/dev_workspace_lease.py acquire --path <PLAN> --session-id <id>`. Renouveler environ toutes les 5 min avec `heartbeat`; le lease expire après 20 min par défaut. À la fin, `release`. Un lease actif d'une autre session interdit l'écriture. Un lease expiré ne se réactive jamais par simple heartbeat : il faut réacquérir.
- Sans lease actif, le `mtime` et le seuil de catégorie restent le fallback. Un agent qui démarre une reprise doit relire le fichier et son diff avant d'écrire.
- Si le fichier change à nouveau après le préflight ou pendant l'édition, même après expiration du délai ou avec un lease précédemment valide, considérer qu'une autre session l'a repris : arrêter l'écriture sur ce chemin et réconcilier avant de continuer.
- L'heure de modification est un signal de concurrence, pas une preuve que le contenu est sémantiquement meilleur. Ne jamais écraser automatiquement un fichier seulement parce qu'un autre exemplaire a un mtime plus récent.

## Git

- Pas de `git worktree` sous `/Users/td/Dev`.
- Travailler dans le checkout canonique en place par défaut. Une branche ou une PR n'est créée que si le workflow du dépôt ou la tâche l'exige explicitement.
- Un clone jetable est autorisé uniquement pour isoler une validation ou une publication/cherry-pick propre. Il ne devient jamais la source de vérité à la place du checkout canonique.
- Committer uniquement les chemins/hunks de la tâche. Jamais `git add -A` par réflexe, jamais de force push, jamais de rebase/reset pour absorber le travail d'une autre session.
- Lors d'une publication depuis un dépôt divergent ou très dirty, préférer un commit borné puis la méthode de cherry-pick documentée par le dépôt dans un clone propre d'`origin/main`, sans embarquer les autres changements locaux.

## Plans

- Un plan ouvert sans modification de contenu depuis plus de 6 jours est automatiquement considéré comme inactif et fermé avec le statut `AUTO_CLOSED_STALE`.
- L'auto-clôture ne signifie pas « terminé ». Elle signifie « ne plus exécuter par défaut ». Le plan reste conservé localement et peut être rouvert explicitement.
- La maintenance utilise le dernier commit du fichier s'il est propre ; pour un plan dirty ou non suivi, elle utilise l'activité locale du fichier afin de ne pas ignorer un travail non committé.
- Réouvrir un plan exige de retirer le marqueur `AUTO_CLOSED_STALE`, de mettre à jour son contenu et son index éventuel.
- Un plan réellement terminé suit ensuite la règle de clôture propre au dépôt : transfert des règles/reliquats utiles, puis suppression/archivage selon les conventions locales.

## Checkouts dupliqués

- Pour plusieurs checkouts ayant le même `origin`, le dépôt dont le nom correspond au nom du remote est le checkout canonique quand il existe.
- Un checkout temporaire dirty n'est jamais supprimé ou écrasé automatiquement. La maintenance le signale comme état local à réconcilier.

<!-- END MANAGED DEV WORKSPACE POLICY -->
