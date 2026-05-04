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
- Taille : 8.8 Milions de mesures

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
 - Taille : 36K mesures

== Water quality data 
#link("https://www.kaggle.com/datasets/sahirmaharajj/water-quality-data")[#underline[[link]]] \
Variété de mesures de la qualité de l'eau sur différents sites
 - Download via login (Kaggle)
 - Format CSV
 - Taille : 2300 mesures

= Europa

== Effets de la pollution atmosphérique sur la santé
#link("https://ec.europa.eu/eurostat/databrowser/view/hlth_cd_iap/default/table?lang=fr")[#underline[[link]]] \
Impact de la pollution sur la santé représenté par année et par pays
 - Libre d'accès (pas de login)
 - Format CSV
 - Taille : 35K mesures

= Pertes économiques provoquées par des situations climatiques extrêmes
#link("https://ec.europa.eu/eurostat/databrowser/view/sdg_13_40/default/table?lang=fr")[#underline[[link]]] \

 - Libre d'accès (pas de login)
 - Format xml
 - Taile : 