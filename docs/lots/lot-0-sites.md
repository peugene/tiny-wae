# Fiche Lot 0 — Sites de surveillance & ingestion Sentinel-2

**Projet** : tiny-wae — POC Earth Intelligence perso
**Statut** : validé — GO Philippe (liste des 25 sites arbitrée) ; historique porté à 48 mois le 21/08
**Date** : 20/08/2026 — transférée le 21/08/2026 depuis un dossier de travail hors dépôt ; **la source est désormais ce fichier**. Déclinaison opérationnelle : chantier `docs/backlog/maturation/lot-0-ingestion/`

---

## 1. Objet du lot

Mettre en place la plomberie données : sélection de ~25 sites, récupération automatisée des
vignettes (chips) Sentinel-2 L2A sur un historique d'un an minimum, masquage nuages,
stockage NAS. Aucune IA dans ce lot — uniquement de l'ingestion fiable et mesurée.

## 2. Paramètres techniques proposés

| Paramètre | Valeur proposée | Justification |
|---|---|---|
| Source données | STAC API `earth-search` (AWS, Element84) en priorité ; Copernicus Data Space (CDSE) en secours | earth-search : sans authentification, COG directs. CDSE : officiel, compte gratuit, quotas |
| Produit | Sentinel-2 L2A (réflectance surface, correction atmosphérique faite) | Le L1C imposerait la correction à notre charge |
| Taille chip | 512 × 512 px @ 10 m = **5,12 × 5,12 km** | Compatible avec les tailles d'entrée des GFMs (multiples de 224/256) |
| Bandes | B02, B03, B04, B08 (10 m) + SCL (masque) ; B11/B12 optionnelles | RGB+NIR = minimum GFM ; SCL = filtrage nuages |
| Filtre nuages | SCL : rejet si > 30 % de pixels nuage/ombre sur le chip | Seuil à ajuster après mesure réelle |
| Historique | **48 mois glissants** (arbitrage Philippe, 20/08/2026) | Saisonnalité + profondeur pour la détection de changement du Lot 2. Archive S2 L2A disponible depuis 2017. Utiliser la collection **harmonized** (changement de baseline janv. 2022 : offset radiométrique corrigé) |
| Stockage | NAS : `/{site_id}/{date}/chip.tif` (GeoTIFF/COG) + `manifest.json` par acquisition | Idempotent, rejouable |

⚠️ **Coordonnées ci-dessous : de mémoire, précision estimée ±1–2 km.** La validation visuelle
de centrage de chaque chip fait partie de l'oracle (§5). Certains mégachantiers dépassent la
taille d'un chip : un segment représentatif est désigné.

## 3. Liste des sites (25)

### Catégorie A — Nucléaire en construction (8) — vérité terrain riche, chronologies publiques

| ID | Site | Pays | Lat, Lon (approx.) | Signature attendue |
|---|---|---|---|---|
| A01 | ITER (Cadarache) | FR | 43.708, 5.776 | Assemblage, bâtiments annexes, parkings |
| A02 | Hinkley Point C | UK | 51.208, −3.130 | Chantier EPR massif — **cas défavorable nuages** |
| A03 | Sizewell C | UK | 52.215, 1.620 | Terrassements en démarrage |
| A04 | Flamanville | FR | 49.536, −1.882 | Post-chantier : activité décroissante |
| A05 | Akkuyu | TR | 36.144, 33.541 | 4 réacteurs en construction, très actif |
| A06 | El Dabaa | EG | 31.043, 28.494 | Chantier actif, ciel clair quasi permanent |
| A07 | Zhangzhou | CN | 23.816, 117.578 | Réacteurs Hualong One en série |
| A08 | Vogtle 3-4 | US | 33.143, −81.762 | Achevé 2023-24 : transition chantier → stable |

### Catégorie B — Mégachantiers mondiaux (9) — signatures énormes, idéal détection de changement

| ID | Site | Pays | Lat, Lon (approx.) | Signature attendue |
|---|---|---|---|---|
| B01 | NEOM "The Line" (segment Hidden Marina) | SA | 28.09, 35.23 | Terrassement massif, désert = ciel clair |
| B02 | Aéroport King Salman (Riyad) | SA | 24.96, 46.70 | Pistes et terminaux en construction |
| B03 | Nouvelle capitale administrative | EG | 30.03, 31.73 | Urbanisation massive |
| B04 | Barrage GERD | ET | 11.215, 35.093 | Niveau du réservoir (saisonnier + remplissage) |
| B05 | Parc solaire M. bin Rashid (Dubaï) | AE | 24.76, 55.36 | Extension par phases datées |
| B06 | Mine d'Escondida | CL | −24.27, −69.07 | Extension fosse/terrils, désert d'Atacama |
| B07 | Salar d'Atacama (bassins lithium) | CL | −23.50, −68.30 | Évolution des bassins d'évaporation |
| B08 | Port de Chancay | PE | −11.57, −77.27 | Mise en service 2024, extension |
| B09 | Autoroute A69 Toulouse-Castres (section) | FR | 43.60, 2.00 | Chantier linéaire — **contrôle local visitable** |

### Catégorie C — Sites stables & veille type OSINT (8) — mesure des faux positifs + thématique surveillance

| ID | Site | Pays | Lat, Lon (approx.) | Rôle |
|---|---|---|---|---|
| C01 | Centrale de Golfech | FR | 44.11, 0.85 | Contrôle négatif nucléaire, proche Toulouse |
| C02 | Airbus Toulouse-Blagnac | FR | 43.63, 1.36 | Contrôle négatif industriel, vérifiable de visu |
| C03 | Port de Fos-sur-Mer | FR | 43.42, 4.85 | Industriel stable, trafic variable |
| C04 | Raffinerie de Lacq | FR | 43.42, −0.62 | Industriel stable |
| C05 | Natanz | IR | 33.72, 51.73 | Veille OSINT documentée, changements épisodiques |
| C06 | Base aérienne d'Engels | RU | 51.48, 46.21 | Veille OSINT documentée |
| C07 | Punggye-ri | KP | 41.28, 129.08 | Site quasi statique, OSINT |
| C08 | Zone témoin rurale (forêt, SO Toulouse) | FR | à définir | Contrôle négatif pur |

**Équilibre** : 12 sites « changement attendu », 8 « stables » (dont 4 contrôles négatifs stricts),
5 intermédiaires. Les stables sont aussi importants que les actifs : c'est eux qui mesurent le
taux de faux positifs du futur Lot 2.

## 4. Livrables du lot

1. Pipeline d'ingestion Python (STAC → chips GeoTIFF sur NAS), idempotent, rejouable, configurable par fichier de sites (YAML/JSON). Chaque étape livrée comme **CLI autonome à I/O explicites, orchestrable par l'outil de workflow CWL de Philippe**.
2. Historique 48 mois ingéré pour les 25 sites.
3. Mode incrémental : le même pipeline, borné par fenêtre temporelle, pour l'ingestion quotidienne des nouvelles acquisitions.
4. Rapport de recette chiffré (voir oracle).
5. Planche de contrôle visuel : 1 mosaïque par site (premier chip, dernier chip) pour validation du centrage.

## 5. Oracle de recette (figé avant implémentation)

| # | Critère | Seuil de succès |
|---|---|---|
| O1 | Centrage : le site est visuellement identifiable et centré sur le chip | 25/25 sites validés sur planche visuelle (gate Philippe) |
| O2 | Historique : nombre d'acquisitions exploitables (< 30 % nuages) par site sur 48 mois | ≥ 60 par site ; **chiffre par site publié, y compris les pires** |
| O3 | Intégrité : chips lisibles, géoréférencés, 4 bandes + SCL présentes | 100 % des chips ingérés |
| O4 | Idempotence : relance du script = zéro doublon, zéro re-téléchargement | vérifié par run double |
| O5 | Volume et durée d'ingestion mesurés | publiés (pas de seuil — c'est la baseline) |

**Non testé dans ce lot** : qualité radiométrique fine, recalage sub-pixel entre dates,
Sentinel-1, tout ce qui touche aux GFMs.

## 6. Risques identifiés

- Sites UK/tropicaux : perte nuages pouvant dépasser 60 % (O2 le mesurera — argument S1 en V2).
- Coordonnées de mémoire : correction possible au moment de la planche visuelle (O1).
- earth-search : pérennité du service non garantie — l'abstraction STAC rend le basculement CDSE peu coûteux.
- The Line : ralentissements de chantier documentés en 2025 — signature possiblement plus faible qu'espéré.
- Historique 48 mois : certains sites n'existaient pas il y a 4 ans (Sizewell, Chancay) — c'est une vérité terrain en soi, pas un défaut d'ingestion. Volume estimé ~15-25 Go total (**non mesuré** — O5 le chiffrera).
