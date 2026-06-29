# Documentation de l'API : Moteurs Mathématiques & Statistiques

Cette documentation couvre le cœur analytique de **Kawakiri**. Les modules
ci-dessous transforment des données brutes en indicateurs statistiques permettant
au pipeline de construire, classer et certifier des modèles décisionnels
dimensionnels [@kimball2013] de manière entièrement déterministe.

Les fonctions sont présentées dans l'ordre d'exécution du pipeline :

```
1.  Ingestion & Profilage de base    →  basic_profile.py
2.  Scoring d'identifiabilité        →  identifiability.py
3.  Score composite d'identifiant    →  identifiability.py
4.  Inférence des clés primaires     →  pk_inference.py
5.  Inférence des jointures          →  join_candidate.py
6.  Construction du graphe           →  adjacency.py
7.  Inférence des rôles              →  role_inference.py
8.  Construction des candidats       →  candidate_builder.py
9.  Ranking                          →  ranking.py
10. Validation (4 règles)            →  *_validator.py
11. Certification                    →  certification.py
12. Export SQL & rapport JSON        →  sql_generator.py / certification_report.py
```

---

## 1. Profilage de base (`basic_profile.py`)

Ces fonctions calculent l'empreinte statistique fondamentale de chaque colonne
lors de la phase d'ingestion [@abedjan2015].

---

### `calculate_sparsity_ratio(column_data)`

Calcule le ratio de vacuité (*Sparsity*) pour évaluer la complétude d'un
attribut [@abedjan2015].

**Formule :**

$$S(C) = \frac{N_{\text{null}}}{N_{\text{total}}}$$

**Interprétation :**

- $S(C) = 1.0$ : colonne entièrement vide, exclue de toute analyse ultérieure.
- $S(C) > 0.0$ : colonne disqualifiée comme clé primaire simple, l'intégrité
  de l'entité n'étant pas garantie.

---

### `calculate_uniqueness_ratio(column_data)`

Évalue le pouvoir discriminant d'une colonne (ou d'un tuple de colonnes) sur
ses valeurs non nulles [@abedjan2015]. Soit $\mathcal{D}(C)$ l'ensemble des
valeurs distinctes.

**Formule :**

$$U(C) = \frac{|\mathcal{D}(C)|}{N_{\text{total}} - N_{\text{null}}}$$

**Interprétation :**

Le pipeline valide l'existence d'une dépendance fonctionnelle stricte (clé
primaire) si et seulement si $U(C) \geq \theta_{\text{uni}}$ (seuil configurable,
valeur par défaut : $0.95$).

---

## 2. Scoring d'identifiabilité (`identifiability.py`)

Ce module analyse la distribution et la diversité de l'information contenue dans
chaque colonne pour classifier sémantiquement les tables [@abedjan2015].

---

### `calculate_shannon_entropy(column_data, normalized=True)`

Calcule l'entropie de Shannon pour mesurer l'incertitude et la diversité des
valeurs d'une distribution [@shannon1948].

**Formule — entropie brute :**

$$H(C) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$

où $P(x_i)$ est la probabilité d'occurrence de la valeur $x_i$ [@shannon1948].

**Formule — entropie normalisée** (retournée par défaut, `normalized=True`) :

$$H_{\text{norm}}(C) = \frac{H(C)}{\log_2(N)}$$

La normalisation par $\log_2(N)$ (entropie maximale théorique) permet de
comparer des tables de tailles différentes sur une échelle $[0, 1]$.

> **Note :** Cette normalisation est volontairement plus stricte que la
> normalisation conventionnelle par $\log_2(n)$ (où $n$ est le nombre de valeurs
> distinctes). Elle approche $1$ uniquement si presque chaque valeur est unique
> ($n \approx N$), ce qui cible précisément les colonnes identifiantes.

**Interprétation :**

- $H_{\text{norm}} \approx 0$ : colonne catégorielle à faible diversité
  (ex. `statut = Actif/Inactif`) → signal Dimension.
- $H_{\text{norm}} \approx 1$ : colonne continue ou identifiante
  (ex. `montant = 12.50, 19.99…`) → signal Fait ou clé primaire.

C'est le pilier du test de **Séparation Sémantique des Rôles** [@kimball2013].

---

### `calculate_coefficient_of_variation(column_data)`

Mesure la dispersion relative des données numériques autour de leur moyenne,
indépendamment de l'unité de mesure [@abedjan2015].

**Formule :**

$$CV(C) = \frac{\sigma}{\mu}$$

où $\sigma$ est l'écart-type et $\mu$ la moyenne.

> **Cas limite :** non défini si $\mu = 0$. La colonne est alors exclue du
> scoring de variabilité.

**Interprétation :**

- $H_{\text{norm}} \approx 1$ **ET** $CV \gg 0$ : la colonne est une
  **mesure de fait** (forte diversité et forte variabilité) [@kimball2013].
- $CV \approx 0$ : constante ou attribut technique → signal Dimension.

---

### `calculate_skewness(column_data)`

Calcule le coefficient d'asymétrie de Fisher pour détecter les déséquilibres
de distribution [@abedjan2015].

**Formule :**

$$\gamma_1 = \frac{\mathbb{E}[(X - \mu)^3]}{\sigma^3}$$

**Interprétation :**

- $\gamma_1 \approx 0$ : distribution symétrique, cohérente avec une clé
  primaire incrémentale.
- $\gamma_1 \gg 1$ : asymétrie extrême, signalant une colonne contenant
  massivement des valeurs par défaut (ex. `9999`) ou des erreurs de saisie.

---

### `calculate_identifiability_score(column_data)`

Calcule un score composite agrégé à partir des quatre métriques précédentes
pour produire un classement unique des candidats à la clé primaire
[@abedjan2015].

**Formule :**

$$I(C) = w_U \cdot U(C) + w_H \cdot H_{\text{norm}}(C) + w_S \cdot (1 - S(C)) - w_\gamma \cdot |\gamma_1(C)|$$

où $w_U$, $w_H$, $w_S$, $w_\gamma$ sont des poids configurables dans le fichier
de contrôle, et le terme $(1 - S(C))$ récompense la complétude.

**Interprétation :**

Un score $I(C)$ élevé indique un candidat fort à la clé primaire. Les colonnes
sont triées par $I(C)$ décroissant avant d'être soumises à l'algorithme glouton
de déduction de clé composite.

---

## 3. Inférence topologique & graphes (`join_candidate.py` et `adjacency.py`)

---

### `calculate_join_success_ratio(source_col, target_col)`

Détermine la viabilité d'une relation Clé Étrangère → Clé Primaire en calculant
le taux d'inclusion ensembliste entre deux domaines de valeurs [@demarchi2002].

**Formule :**

Soit $T_s$ la table source et $T_t$ la table cible (clé primaire $K_t$) :

$$JSR(C_s \rightarrow K_t) = \frac{|\pi_{C_s}(T_s) \cap \pi_{K_t}(T_t)|}{|\pi_{C_s}(T_s)|}$$

**Interprétation :**

Un arc est créé dans le graphe si $JSR \geq \theta_{jsr}$ (seuil configurable,
valeur par défaut : $0.95$). Ce calcul constitue la base de la validation de
l'**intégrité référentielle** du modèle [@kimball2013].

---

### `build_adjacency_matrix(tables, joins)`

Construit la représentation mathématique du schéma relationnel sous forme de
graphe orienté [@lehner1998].

**Formule :**

La matrice d'adjacence binaire $A$ de taille $N \times N$ est définie telle que
pour deux tables $T_i$ et $T_j$ :

$$A_{i,j} = \begin{cases} 1 & \text{si } JSR(T_i \rightarrow T_j) \geq \theta_{jsr} \\ 0 & \text{sinon} \end{cases}$$

**Interprétation :**

La matrice $A$ est le point d'entrée de toutes les étapes suivantes : inférence
des rôles, détection de cycles, construction des candidats et validation
structurelle.

---

## 4. Construction & évaluation des modèles (`role_inference.py` et `ranking.py`)

---

### `infer_table_roles(adjacency_matrix, entropy_scores)`

Détermine le rôle architectural d'une table (Fait, Dimension ou Isolée) en
combinant la théorie des graphes et les scores sémantiques, selon la
méthodologie de modélisation dimensionnelle [@kimball2013] et les formes
normales multidimensionnelles [@lehner1998].

**Logique de décision :**

| Rôle | Critères |
|---|---|
| **Dimension** | In-degree $> 0$ dans $A$ ET $\overline{H_{\text{norm}}}$ faible [@kimball2013] |
| **Fait** | Out-degree maximal ET In-degree nul ou faible ET $\overline{CV}$ élevé [@kimball2013] |
| **Isolée** | In-degree $= 0$ ET Out-degree $= 0$ (élagué du modèle candidat) |

---

### `calculate_model_score(candidate_model)`

Génère un score de viabilité permettant de classer les architectures candidates.
Inspiré du **Rasoir d'Ockham** : favoriser le modèle le plus simple qui explique
le mieux les données [@kimball2013].

**Formule :**

$$\mathbb{S}(M) = \sum_{i} w_i \cdot f_i(M) - \sum_{j} p_j \cdot g_j(M)$$

où :

- $f_i(M)$ sont les **termes de récompense** : nombre de jointures Fait →
  Dimension validées, nombre d'attributs numériques (mesures), nombre de
  dimensions connectées,
- $g_j(M)$ sont les **termes de pénalité** : nombre total de tables, présence
  de tables intermédiaires redondantes,
- $w_i$ et $p_j$ sont des poids configurables dans le fichier de contrôle.

Les candidats sont triés par $\mathbb{S}$ décroissant. En cas d'égalité, le
départage est effectué par le nombre d'attributs numériques couverts.

---

## 5. Moteur de validation des candidats

Les quatre règles s'appliquent dans l'ordre indiqué. Un modèle n'accède à la
règle $n+1$ que s'il a passé la règle $n$.

---

### `validate_structural_topology(adjacency_matrix)` — Règle Niveau 1

Applique un parcours en profondeur (DFS) pour vérifier que la matrice
d'adjacence forme un **Graphe Orienté Acyclique (DAG)** [@lehner1998]. La
détection d'un seul cycle disqualifie le modèle (prévention des boucles de
jointure infinies lors des requêtes analytiques).

---

### `validate_semantic_homogeneity(fact_table, dim_table)` — Règle Niveau 2

Vérifie l'étanchéité sémantique entre la table de faits et ses dimensions,
conformément au principe de séparation des rôles [@kimball2013]. Soit $F$
l'ensemble des colonnes de la table de faits et $D$ celles de la dimension
(hors clés de jointure $K$) :

$$( F \setminus K ) \cap ( D \setminus K ) = \emptyset$$

Cette règle détecte les colonnes apparaissant simultanément dans un Fait et une
Dimension, signe d'une modélisation ambiguë ou d'une dénormalisation incorrecte
[@lehner1998].

---

### `validate_deterministic_granularity(table, pk_columns)` — Règle Niveau 3

Valide l'absence de doublons cachés sur les entités, garantissant que le grain
du fait est déterministe [@kimball2013]. Pour une table $T$ et un grain défini
par les colonnes $PK$ [@lehner1998] :

$$\text{Count}(T) = \text{Count}\!\left(\text{Distinct}\!\left(\pi_{PK}(T)\right)\right)$$

Un tuple dupliqué signale une granularité inadaptée : soit une clé manquante
dans le grain, soit une clé composite incomplète.

---

### `validate_aggregation_stability(fact_table, dim_table, measure_col)` — Règle Niveau 4

Règle la plus critique : vérifie l'absence de produit cartésien involontaire
(*Fan-Out*) lors d'un *Roll-Up* sur une dimension inférée [@kimball2013].

**Étape 1 — Somme au grain fin :**

$$\Sigma_{\text{fine}} = \sum_{i \in F} M_i$$

**Étape 2 — Simulation de l'agrégation :**

$$\Sigma_{\text{agg}} = \sum_{g \in \pi_A(D)} \left( \sum_{k \in \{F \bowtie D\}_{A=g}} M_k \right)$$

**Étape 3 — Validation :**

$$\Delta = |\Sigma_{\text{fine}} - \Sigma_{\text{agg}}| \leq \epsilon$$

où $\epsilon$ est la tolérance machine (Float64).

Si $\Delta > \epsilon$, la relation est rejetée : la granularité de la jointure
est incorrecte et produirait des sommes erronées en production.

> **Hypothèse implicite :** ce test suppose une relation 1:N sur la clé de
> jointure testée. Un attribut multivalué légitimement dupliqué doit être
> pré-agrégé ou exclu avant cette étape [@kimball2013].

---

## 6. Certification & export (`certification.py` et `sql_generator.py`)

---

### `certify_model(model_score, validations)`

Combine de manière booléenne les résultats des quatre règles de validation
[@kimball2013]. Un modèle reçoit le statut `is_certified = True` si et
seulement si :

$$\prod_{i=1}^{4} \text{Valid}_i = 1$$

c'est-à-dire qu'aucune règle n'a été invalidée. Le rapport de certification
expose le détail des règles passées, des avertissements et des problèmes
détectés, ainsi qu'un score de certification $\in [0, 100]$.

---

### `generate_sql_view(certified_model)`

Traduit de manière déterministe le graphe certifié en requête SQL analytique
(dialecte ClickHouse [@clickhouse]), en convertissant les relations validées
($A_{i,j} = 1$) en opérateurs `LEFT JOIN` [@kimball2013].

**Exemple de sortie (schéma en étoile à 4 dimensions) :**

```sql
SELECT
    f.sale_id         AS fact_sale_id,
    f.revenue         AS fact_revenue,
    d1.date_id        AS calendar_date_id,
    d1.month_name     AS calendar_month_name,
    d2.customer_name  AS customers_customer_name,
    d3.product_name   AS products_product_name,
    d4.carrier        AS shipments_carrier
FROM `schema`.`sales` AS f
LEFT JOIN `schema`.`calendar`  AS d1 ON f.date_id     = d1.date_id
LEFT JOIN `schema`.`customers` AS d2 ON f.customer_id = d2.customer_id
LEFT JOIN `schema`.`products`  AS d3 ON f.product_id  = d3.product_id
LEFT JOIN `schema`.`shipments` AS d4 ON f.sale_id     = d4.sale_id
```
