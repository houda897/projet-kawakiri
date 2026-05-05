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

#align(center)[
  #text(size: 22pt, weight: "bold")[Ressources BDD]
  \ 
  #text(size: 10pt)[#datetime.today().display("[day]/[month]/[year]")]
]

\ \ 

= Copernicus 
#link("https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description")[#underline[[link]]] \

*Global Ocean Physics Analysis and Forecast* : 
- Donwload via login
- Format NetCDF
- Dimensions : time[1], depth[1], lalitude[2041], longitude[4320]
- Mesures : température, salinité, courant, niveau de la mer
- Taille : 8.8 Milions de mesures (18ko)

= Kaggle

== Deap : Deciphering Environmental Air Pollution 
#link("https://www.kaggle.com/datasets/mayukh18/deap-deciphering-environmental-air-pollution")[#underline[[link]]] \
Dataset sur la pollution de l'air dans différentes villes. 
- Download via login (Kaggle)
- Format CSV
- Dimensions :
 - Date
 - City
 - X_median: Valeur médiane du polluant X par jour
 - mil_miles: Distance totale parcourue pendant le sample
 - pp_feat: Caractéristique calculée pour l'influence des centrales électriques voisines
 - Population Staying at Home: Mesure d'émmision domestique
- Polluants: 
 - PM2.5, PM10, NO2, O3, CO, SO2
- Mesures météorologique :
 - Temperature, Pressure, Humidity, Dew, Wind Speed, Wind Gust
- Taille : 36K mesures (13Mo)

== Water quality data 
#link("https://www.kaggle.com/datasets/sahirmaharajj/water-quality-data")[#underline[[link]]] \
Variété de mesures de la qualité de l'eau sur différents sites
- Download via login (Kaggle)
- Format CSV
- Taille : 2300 mesures (177ko)

= Europa

== Effets de la pollution atmosphérique sur la santé
#link("https://ec.europa.eu/eurostat/databrowser/view/hlth_cd_iap/default/table?lang=fr")[#underline[[link]]] \
Impact de la pollution sur la santé représenté par année et par pays
- Libre d'accès (pas de login)
- Format CSV
- Taille : 35K mesures (50ko)
- Differentes tables


== Pertes économiques provoquées par des situations climatiques extrêmes
#link("https://ec.europa.eu/eurostat/databrowser/view/sdg_13_40/default/table?lang=fr")[#underline[[link]]] \

- Libre d'accès (pas de login)
- Format xml
- Taile : 4720 Mesures (87ko)
- Differentes tables


== Pollution, saleté ou autres problèmes environnementaux
#link("https://ec.europa.eu/eurostat/databrowser/view/ilc_mddw02/default/table?lang=fr")[#underline[[link]]]

Jeu de donnée regroupant: Personne en risque de pauvreté ou exclusion sociale, inégalité de salaire, répartition des revenus et pauvreté monétaire, condition de vie et privation matérielle.
- Libre d'accès (pas de login)
- Format CSV
- Taile : 35K Mesures (5Mo)
- Differentes tables


= AQUASTAT 

== Système d'information mondial de la FAO sur l'eau et l'agriculture
#link("https://data.apps.fao.org/aquastat/?lang=fr")[#underline[[link]]] \

- Libre accès (pas de login)
- Format CSV
- Taille : 50K mesures (7Mo)
- Differentes tables
- Catégories :
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

= EOCD

== Terrestrial protected area by designation type
#link("https://data-explorer.oecd.org/vis?fs[0]=Topic%2C1%7CEnvironment%23ENV%23%7CBiodiversity%23ENV_BIO%23&pg=0&fc=Topic&bp=true&snb=3&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_PA%40DF_PROT_AREA&df[ag]=OECD.ENV.EPI&df[vs]=1.0&pd=%2C&dq=.A.TERRESTRIAL.PT_LAR.ALL_INC_P.TCEOA.CNTRY&to[TIME_PERIOD]=false")[#underline[[link]]]

- Libre accès (pas de login)
- Format CSV
- Taille : 286K mesures (1Go)
- Differentes tables