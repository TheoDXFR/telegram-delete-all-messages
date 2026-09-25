<!-- BEGIN MANAGED DEV WORKSPACE POLICY -->

# Politique de travail partagée — /Users/td/Dev

Cette politique s'applique à tous les dépôts canoniques sous `/Users/td/Dev`. Elle prime sur les anciennes règles Git/concurrence incompatibles. Les règles métier propres à chaque dépôt restent prioritaires hors de ce périmètre.

## État local et concurrence

- Le contenu du checkout local canonique est la base de travail. `HEAD` et `origin/*` servent à comparer et publier, jamais à effacer automatiquement un état local.
- Un arbre `dirty` n'est pas une erreur. Ne jamais utiliser `stash`, `restore`, `reset`, `checkout -- <fichier>` ou `clean` pour obtenir artificiellement un arbre propre ou contourner un conflit de session.
- Avant d'éditer, raisonner par chemin, pas par statut global. Lire le fichier courant et son diff éventuel.
- Une modification récente par une autre session **n'interdit pas à elle seule l'écriture**. Le mode normal est la réconciliation optimiste : relire la version courante juste avant d'écrire, conserver ses octets comme base, puis appliquer uniquement un patch borné qui préserve les changements déjà présents.
- Si le contexte exact ou le hunk ciblé est toujours compatible, l'édition peut être faite immédiatement, même si le fichier vient d'être modifié par un autre LLM. Après écriture, vérifier le diff utile et l'absence de disparition inattendue d'un changement étranger.
- Si la zone ciblée a changé depuis le préflight, relire et rebaser le patch sur la nouvelle version. Ne jamais réappliquer une ancienne copie complète du fichier. Si les deux changements touchent la même unité logique et ne peuvent pas être fusionnés sans arbitrage, ne pas écrire cette zone tant qu'elle n'est pas réconciliée.
- Les délais d'inactivité deviennent uniquement un **fallback de reprise** lorsqu'une réconciliation sûre ne peut pas être démontrée, notamment pour une réécriture complète, un générateur non fusionnable ou un fichier structurant modifié sur la même zone :
  - `PLAN_*.md` et `docs/plans/README.md` / `plans/README.md` : **30 min** sans activité ;
  - fichier ordinaire : **60 min** sans activité ;
  - fichier à fort rayon d'explosion : **90 min** sans activité. Cette classe couvre au minimum `AGENTS.md`, `/Users/td/Dev/agent-skills/policies/dev-workspace.md`, les lockfiles partagés, les manifests/configs structurants listés par `/Users/td/Dev/agent-skills/scripts/dev_workspace_lease.py`, les workflows CI et les plists.
- Un délai expiré signifie seulement **« reprise prudente autorisée après préflight »**, jamais « tâche terminée » ni « contenu abandonné ». Le délai n'autorise jamais à revenir à `HEAD` ni à écraser les octets locaux.
- Un lease borné est recommandé quand plusieurs sessions risquent de réécrire la même unité logique ou quand l'opération n'est pas fusionnable proprement : `python3 /Users/td/Dev/agent-skills/scripts/dev_workspace_lease.py acquire --path <PLAN> --session-id <id>`. Renouveler environ toutes les 5 min avec `heartbeat`; le lease expire après 20 min par défaut. À la fin, `release`. Un lease actif d'une autre session interdit l'écriture sur la cible protégée. Un lease expiré ne se réactive jamais par simple heartbeat : il faut réacquérir.
- Sans lease actif, le `mtime` et le seuil de catégorie ne servent qu'au fallback ci-dessus. Pour une édition bornée et réconciliable, ils ne constituent pas un verrou.
- Si le fichier change à nouveau après le préflight ou pendant l'édition, recommencer le préflight sur la version courante et réconcilier le patch. Ne poursuivre que si le changement peut toujours être appliqué sans supprimer ni inverser le travail concurrent.
- L'heure de modification est un signal de concurrence, pas une preuve que le contenu est sémantiquement meilleur. Ne jamais écraser automatiquement un fichier seulement parce qu'un autre exemplaire a un mtime plus récent.

## Git

- Pas de `git worktree` sous `/Users/td/Dev`.
- Travailler dans le checkout canonique en place par défaut. Une branche ou une PR n'est créée que si le workflow du dépôt ou la tâche l'exige explicitement.
- Un clone jetable est autorisé uniquement pour isoler une validation ou une publication/cherry-pick propre. Il ne devient jamais la source de vérité à la place du checkout canonique.
- Committer uniquement les chemins/hunks de la tâche. Jamais `git add -A` par réflexe, jamais de force push, jamais de rebase/reset pour absorber le travail d'une autre session.
- Lors d'une publication depuis un dépôt divergent ou très dirty, préférer un commit borné puis la méthode de cherry-pick documentée par le dépôt dans un clone propre d'`origin/main`, sans embarquer les autres changements locaux.
- Un clone de publication doit réactiver explicitement les hooks du dépôt avant le push quand le dépôt versionne un `.githooks/` : par exemple `git config core.hooksPath .githooks`. Ne jamais supposer que `core.hooksPath` est transporté par le clone.
- Si la divergence locale/distante est constituée de commits équivalents dont l'arbre est identique hors tâche, ne pas perdre du temps à réconcilier l'historique local : publier uniquement le commit borné de la tâche depuis un clone propre de `origin/main`.

## Validations, builds et publication

- Une preuve verte récente est réutilisable si elle couvre le patch exact ou le commit exact et qu'aucune source, test, configuration ou dépendance pertinente n'a changé depuis. Ne pas rejouer une suite coûteuse uniquement parce qu'on passe de « terminé localement » à « publier ».
- Rejouer une validation seulement si le diff pertinent a changé, si la preuve précédente était partielle ou en échec, si un hook obligatoire l'impose, ou si l'environnement a changé d'une manière qui invalide réellement la preuve.
- Si le hook `pre-push` exécute déjà `check`, build, audits ou tests lourds, ne pas lancer immédiatement les mêmes commandes juste avant le push sans raison de diagnostic. Préférer les preuves exactes déjà acquises puis laisser le hook obligatoire jouer son rôle.
- Avant tout build, Playwright ou suite UI qui écrit dans `dist/`, `.astro/`, `test-results/`, `coverage/` ou un répertoire généré partagé, vérifier les processus actifs du même dépôt, les ports utilisés et les autres writers plausibles. Deux suites susceptibles d'écrire dans les mêmes sorties ne doivent pas tourner simultanément dans le même checkout.
- En cas de writer concurrent, choisir dans cet ordre : réutiliser une preuve exacte déjà verte ; isoler réellement la validation avec sorties, ports et dépendances indépendants ; seulement sinon différer la suite conflictuelle. Ne jamais arrêter un runner étranger uniquement pour faire passer sa propre validation.
- Un échec `ERR_CONNECTION_REFUSED`, trace Playwright manquante, fichier généré disparu, `ENOSPC` ou corruption de sortie observé pendant une concurrence active est d'abord un incident d'environnement. Confirmer la cause avant de conclure à une régression produit ou de relancer toute la DoD.
- Avant un clone lourd, `npm ci`, build complet ou génération volumineuse, vérifier l'espace disque. Si l'espace est contraint, ne pas dupliquer aveuglément `node_modules` ou des caches ; préférer une preuve déjà valide, une isolation légère compatible avec l'outil, ou le contrôle obligatoire du hook.
- Pour Astro/Vite et outils sensibles aux chemins réels, ne pas symlinker un `node_modules` d'un autre checkout pour simuler une isolation : le resolver peut mélanger les chemins et produire de faux échecs. Utiliser des dépendances réellement locales, des hardlinks/copies compatibles si l'espace le permet, ou ne pas dupliquer la validation.
- Toute validation supplémentaire doit répondre à une question encore ouverte. Une nouvelle boucle qui ne peut rien apprendre de plus que les preuves déjà acquises est du travail inutile et doit être supprimée.

## Plans

- **État courant lisible en tête.** Une reprise fraîche doit comprendre sans parcourir tout le journal : objectif courant, périmètre, hors-périmètre, critères de clôture, nombre de reliquats ouverts et **au maximum 3 prochaines actions**. Pour un ancien plan, mettre à jour ce bloc compact au lieu de réécrire tout l'historique.
- **Pas d'élargissement silencieux.** Une nouvelle demande causalement indépendante part dans un autre plan, une roadmap ou une note dédiée. Si elle est indispensable au même objectif, l'intégration est tracée par une entrée `SCOPE_ADD` avec motif, impact sur la clôture et chemins concernés.
- **Statuts avant journal.** Après chaque lot terminé ou publié, mettre à jour d'abord l'en-tête/tableau canonique puis ajouter au besoin un checkpoint. Un item soldé ne reste pas `PARTIEL` parce qu'un vieux checkpoint le disait.
- **STOP compact.** Un arrêt demandé produit un seul checkpoint canonique : état fonctionnel, `HEAD`/`origin`, seuls chemins possédés par la session, blocages, prochaine action exacte et processus à ne pas arrêter. Ne pas recopier tout l'historique.
- **Journal compact, preuves ailleurs.** Garder dans le plan les jalons et arbitrages utiles ; sorties longues, SHA détaillés, captures et diagnostics vont dans `.agent-missions/<plan>/` ou un artefact lié. Une compaction ne perd jamais un arbitrage, une preuve nécessaire ni un reliquat ouvert.
- **Préflight incrémental.** Mémoriser le dernier `HEAD`/`origin` contrôlé et les tokens/hash/mtime des chemins cibles dans le checkpoint ou l'artefact de preuve. Si ces entrées sont inchangées, réutiliser le diagnostic précédent ; refaire seulement l'anti-race juste avant écriture ou publication.
- **Frontière Git unique.** Publier un lot par commit borné, puis faire **une seule réconciliation finale du checkout partagé par dépôt**. Une réconciliation intermédiaire n'est justifiée que si le runtime doit réellement charger le nouveau code ou si elle débloque le lot suivant.
- **Clôture avant extension.** Avant d'ouvrir un nouveau lot dans le même plan, fermer ou transférer les items déjà terminés et recalculer les 1 à 3 prochaines actions. Un plan ne sert pas de parapluie à des chantiers indépendants.
- **Overrides traçables, jamais de seuil rigide aveugle.** Toute limite de taille, durée, nombre d'étapes ou concurrence garde un override explicite et motivé pour les vrais plans complexes ; l'override ne supprime pas les invariants Git, sécurité ou préservation du travail concurrent.
- Un plan ouvert sans modification de contenu depuis plus de 6 jours est automatiquement considéré comme inactif et fermé avec le statut `AUTO_CLOSED_STALE`.
- L'auto-clôture ne signifie pas « terminé ». Elle signifie « ne plus exécuter par défaut ». Le plan reste conservé localement et peut être rouvert explicitement.
- La maintenance utilise le dernier commit du fichier s'il est propre ; pour un plan dirty ou non suivi, elle utilise l'activité locale du fichier afin de ne pas ignorer un travail non committé.
- Réouvrir un plan exige de retirer le marqueur `AUTO_CLOSED_STALE`, de mettre à jour son contenu et son index éventuel.
- Un plan réellement terminé suit ensuite la règle de clôture propre au dépôt : transfert des règles/reliquats utiles, puis suppression/archivage selon les conventions locales.

## Checkouts dupliqués

- Pour plusieurs checkouts ayant le même `origin`, le dépôt dont le nom correspond au nom du remote est le checkout canonique quand il existe.
- Un checkout temporaire dirty n'est jamais supprimé ou écrasé automatiquement. La maintenance le signale comme état local à réconcilier.

<!-- END MANAGED DEV WORKSPACE POLICY -->
