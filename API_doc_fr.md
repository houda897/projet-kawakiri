## Documentation de l'API : Moteurs Mathématiques & Statistiques

Cette section documente les fonctions du cœur analytique de Kawakiri. Ces modules transforment les données brutes en indicateurs statistiques permettant à notre pipeline de prouver mathématiquement la validité d'un modèle décisionnel.

## Moteur de Profilage de Base (basic_profile.py)

Ces fonctions calculent l'empreinte fondamentale de chaque colonne lors de l'ingestion.

### `calculate_sparsity_ratio(column_data)`

Calcule le ratio de vacuité (Sparsity) pour déterminer la complétude d'un attribut.

- **Formule Mathématique** :
    
    $$S(C) = \frac{N_{null}}{N_{total}}$$

- **Preuve d'Exclusion** :
    
     Si $S(C)=1.0$, la colonne est vide. Si $S(C)>0.0$, la colonne est mathématiquement disqualifiée pour être une Clé Primaire simple, car l'intégrité de l'entité n'est pas garantie.

### `calculate_uniqueness_ratio(column_data)`

Évalue le pouvoir discriminant d'une colonne (ou d'un tuple de colonnes) sur ses valeurs non nulles. Soit $\mathcal{D}(C)$ l'ensemble des valeurs distinctes.

- **Formule Mathématique** :
    
    $$U(C) = \frac{|\mathcal{D}(C)|}{N_{total} - N_{null}}$$

- **Preuve d'Inférence (Clés Primaires)** : 

    Le système prouve l'existence d'une dépendance fonctionnelle stricte (Clé Primaire) si et seulement si $U(C) ≥ \theta_{uni}$​ (où $\theta_{uni}$​ est notre seuil de tolérance, ex: 0.95).

## Moteur de Théorie de l'Information (identifiability.py)

Ce module analyse la distribution et la diversité de l'information pour classifier sémantiquement les tables.

### `calculate_shannon_entropy(column_data, normalized=True)`

Calcule l'entropie de Shannon pour mesurer l'incertitude et la diversité des valeurs d'une distribution.

- **Formule Mathématique** :
    L'entropie brute est calculée via la probabilité d'occurrence $P(x_i​)$ de chaque valeur distincte :
    
    $$H(C) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$

    Pour comparer des tables de tailles différentes, l'API retourne l'entropie normalisée (divisée par l'entropie maximale théorique $log_2​(N)$) :
    
    $$H_{norm}(C) = \frac{H(C)}{\log_2(N)}$$

- **Preuve Sémantique** : 

    Une dimension catégorielle (ex: `Statut = Actif/Inactif`) présentera un $H_{norm}$​ proche de 0. 
    Une mesure continue (ex: `Montant = 12.50, 19.99...`) ou un identifiant aura un $H_{norm}$​ proche de 1. 
    C'est le pilier du test de Séparation des Rôles.

### `calculate_coefficient_of_variation(column_data)`

Mesure la dispersion relative des données numériques autour de leur moyenne, indépendamment de leur échelle (euros, kilogrammes, etc.).

- **Formule Mathématique** :
    
    $$CV(C) = \frac{\sigma}{\mu}$$

    (Où $\sigma$ est l'écart-type et μ la moyenne).

    Preuve Sémantique : Si $H_{norm} ​≈ 1$ AND $CV ≫ 0$ (beaucoup plus que 0), l'API prouve que la colonne est une **Mesure de Fait** (elle varie beaucoup et de manière imprévisible). Si $CV ≈ 0$, c'est une constante ou un attribut technique (Dimension).

### `calculate_skewness(column_data)`

Calcule le coefficient d'asymétrie de Fisher pour identifier les déséquilibres dans la distribution.

- **Formule Mathématique** :
    
    $$\gamma_1 = \frac{E[(X - \mu)^3]}{\sigma^3}$$

- **Preuve de Détection d'Anomalie** : Une clé primaire incrémentale a une distribution uniforme ($\gamma_1 ​≈ 0$). Une asymétrie extrême ($\gamma_1 ​≫ 1$) prouve une distribution anormale, signalant souvent une colonne contenant massivement des valeurs par défaut (ex: `9999`) ou des erreurs de saisie.

## Moteur d'Inférence des Jointures (join_candidate.py)

### `calculate_join_success_ratio(source_col, target_col)`

Détermine la viabilité d'une relation de type $Clé Étrangère → Clé Primaire$ en calculant le taux d'inclusion ensembliste.

- **Formule Mathématique** :
    Soit $T_s$​ la table source et $T_t$​ la table cible (clé primaire $K_t$​).
    
    $$JSR(C_s \rightarrow K_t) = \frac{|\pi_{C_s}(T_s) \cap \pi_{K_t}(T_t)|}{|\pi_{C_s}(T_s)|}$$

- **Preuve de Relation** : L'API prouve l'existence d'une relation (arc dans le graphe) si le $JSR$ franchit le seuil probabiliste $\theta_{jsr}$​ (ex: 0.95). Ce calcul valide **l'Intégrité Référentielle** du modèle.

## Moteur de Validation des Agrégations (aggregation_stability_validator.py)

C'est la fonction la plus critique de l'API. Elle prouve l'absence de produit cartésien involontaire (Fan-Out).

### `validate_aggregation_stability(fact_table, dim_table, measure_col)`

Vérifie la loi de conservation des mesures lors d'un Roll-Up sur une dimension inférée.

- **Formule Mathématique** :
    L'API calcule la somme au grain fin $\Sigma_{fine}$​ :

    $$\Sigma_{fine} = \sum_{i \in F} M_i$$

    Puis simule l'agrégation via la jointure inférée ($\Sigma_{agg}$) :

    $$\Sigma_{agg} = \sum_{g \in \pi_A(D)} \left( \sum_{k \in \{F \bowtie D\}_{A=g}} M_k \right)$$

    Le Delta est évalué contre une tolérance machine $\epsilon$ (Float64) :

    $$\Delta = |\Sigma_{fine} - \Sigma_{agg}|$$

- **Preuve de Stabilité** : Le modèle est certifié si et seulement si $\Delta ≤ \epsilon$. Si $\Delta > \epsilon$, l'API prouve mathématiquement que la granularité de la jointure est incorrecte (duplication de lignes) et rejette la relation.