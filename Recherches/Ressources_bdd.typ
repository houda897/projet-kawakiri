#set document(
  title: "Ressources_bdd",
  author: "BERGER Maxime",
)

#set page(
  paper: "a4",
  margin: (x: 2.5cm, y: 2.5cm),
  numbering: "1",
)

#set text(
  font: "Liberation Serif",
  size: 11pt,
  lang: "fr",
)

#let bdd_table(..content) = table(
  columns: (auto, 1fr),
  inset: 10pt,
  align: horizon,
  stroke: 0.5pt + gray,
  fill: (col, row) => if col == 0 { silver.lighten(60%) } else { white },
  ..content
)

#align(center)[
  #text(size: 22pt, weight: "bold")[Ressources BDD]
  \ 
  #text(size: 10pt)[#datetime.today().display("[day]/[month]/[year]")]
]

\ \ 

= Copernicus 


*Global Ocean Physics Analysis and Forecast* : 
#link("https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description")[#underline[[link]]] \
#set text(font: "Linux Libertine", size: 10pt)

#bdd_table(  
  [*Catégorie*], [*Détails*],
  
  [Format / Source], [NetCDF-4],
  [Dimensions], [Time [1], Depth [1], Lat [2041], Lon [4320]],
  [Variables clés], [
    - pH (sea_water_ph_reported_on_total_scale)
    - Alcalinité totale (mol m-3)
    - Carbone inorganique dissous (mol m-3)
  ],
  [Taille],[8.8 Milions de mesures (18ko)],
  [Download],[Login necessaire]
)

= Kaggle

== Deap : Deciphering Environmental Air Pollution 
#link("https://www.kaggle.com/datasets/mayukh18/deap-deciphering-environmental-air-pollution")[#underline[[link]]] \

Dataset sur la pollution de l'air dans différentes villes. 

#bdd_table(
  [*Catégorie*], [*Détails*],

  [Format], [CSV],
  [Dimensions], [
    - Date
    - City
    - X_median: Valeur médiane du polluant X par jour
    - mil_miles: Distance totale parcourue pendant le sample
    - pp_feat: Caractéristique calculée pour l'influence des centrales électriques voisines
    - Population Staying at Home: Mesure d'émmision domestique],
  [Variables clés], [Polluants : PM2.5, PM10, NO2, O3, CO, SO2],
  [Taille], [36K lignes (13Mo)],
  [Download],[Login necessaire]
)

#pagebreak()
== Water quality data 
#link("https://www.kaggle.com/datasets/sahirmaharajj/water-quality-data")[#underline[[link]]] \

Variété de mesures de la qualité de l'eau sur différents sites
#bdd_table(
  [*Catégorie*], [*Détails*],
  [Format], [CSV],
  [Variables clés], [
    - Physique : Température (Eau/Air), Profondeur (Totale/Secchi)
    - Chimie : pH, Salinité (ppt), Oxygène dissous (mg/L)
  ],
  [Période couverte], [1994 - 2019 (Données annuelles/mensuelles)],
  [Localisation], [Identifiants de sites (ex: "Bay")],
  [Taille], [2300 lignes (177ko)],
  [Download],[Login necessaire]
)


= Europa

== Effets de la pollution atmosphérique sur la santé
#link("https://ec.europa.eu/eurostat/databrowser/view/hlth_cd_iap/default/table?lang=fr")[#underline[[link]]] \

Impact de la pollution sur la santé représenté par année et par pays
#bdd_table(
  [*Catégorie*], [*Détails*],
  [Format], [CSV],
  [Variables clés], [
    - Indicateur : Années de vie perdues
    - Polluant : Particules fines
    - Données : Valeurs brutes (Nombre) par pays
  ],
  [Couverture], [38 zones géographiques (Europe), 2014 - 2023],
  [Taille], [35K lignes (50ko)],
  [Download],[Pas de login necessaire]
)

#pagebreak()
== Pertes économiques provoquées par des situations climatiques extrêmes
#link("https://ec.europa.eu/eurostat/databrowser/view/sdg_13_40/default/table?lang=fr")[#underline[[link]]] \

#bdd_table(
  [*Catégorie*], [*Détails*],
  [Format], [XML],
  [Dimensions], [Fréquence, valeur annuelle, moyenne sur 30ans],
  [Taille], [4720 lignes (87ko)],
  [Download],[Pas de login necessaire]
)


== Pollution, saleté ou autres problèmes environnementaux
#link("https://ec.europa.eu/eurostat/databrowser/view/ilc_mddw02/default/table?lang=fr")[#underline[[link]]]

Jeu de donnée regroupant: Personne en risque de pauvreté ou exclusion sociale, inégalité de salaire, répartition des revenus et pauvreté monétaire, condition de vie et privation matérielle.

#bdd_table(
  [*Catégorie*], [*Détails*],
  [Format], [CSV],
  [Taille], [35K lignes (5Mo)],
  [Download],[Pas de login necessaire]
)

#pagebreak()
= AQUASTAT 

== Système d'information mondial de la FAO sur l'eau et l'agriculture
#link("https://data.apps.fao.org/aquastat/?lang=fr")[#underline[[link]]] \

#bdd_table(
  [*Catégorie*], [*Détails*],
  [Format], [CSV],
  [Catégories], [
    - utilisation des sols: superficie totale, terres arables et cultures permanentes
    - population: totale, urbaine et rurale
    - ressources en eau conventionnelles: eaux de surface et eaux souterraines
    - sources d'eau non conventionnelles: eaux usées, eau dessalée et eaux fossiles
    - prélèvement d'eau par secteur: prélèvement d'eau agricole, domestique et industrielle
    - par source: eau de surface, eau souterraine et eau non conventionnelle
    - potentiel d'irrigation
    - surface irriguée ou gestion de l'eau agricole
    - techniques d'irrigation: de surface, aspersion et localisées
    - zones drainées
    - cultures irriguées: superficie et rendement
  ],
  [Taille], [50K lignes (7Mo)],
  [Download],[Pas de login necessaire]
)

= EOCD

== Terrestrial protected area by designation type
#link("https://data-explorer.oecd.org/vis?fs[0]=Topic%2C1%7CEnvironment%23ENV%23%7CBiodiversity%23ENV_BIO%23&pg=0&fc=Topic&bp=true&snb=3&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_PA%40DF_PROT_AREA&df[ag]=OECD.ENV.EPI&df[vs]=1.0&pd=%2C&dq=.A.TERRESTRIAL.PT_LAR.ALL_INC_P.TCEOA.CNTRY&to[TIME_PERIOD]=false")[#underline[[link]]]

Proportion des zones protégés en fonction de pays.
#bdd_table(
  [Format], [CSV],
  [Taille], [286K lignes (1Go)],
  [Download],[Pas de login necessaire]
)