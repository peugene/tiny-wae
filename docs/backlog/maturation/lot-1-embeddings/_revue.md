# Revue de cohérence adversariale — Chantier Lot 1 Embeddings (v1)

**Date** : 24/08/2026 · **Orchestrateur** : architecte/PO (Cowork) · **Protocole** : 5 angles
Opus indépendants et aveugles (découpage, séquençage, faits externes avec vérification à la
source — code des dépôts Clay et TerraTorch, cartes HF —, couverture des décisions actées,
effort/oracles) + réfutation Opus indépendante avec obligation de preuve. Les décisions
actées par le PO étaient explicitement réfutables.

**Chiffres de la revue** : **116 findings bruts** (D:20 · S:18 · F:15 · C:28 · E:35) →
**24 clusters** → réfutation : **13 confirmés · 6 confirmés avec correction · 5 partiels ·
0 réfuté en bloc** (4 sous-findings réfutés à l'intérieur de clusters retenus). Le réfuteur
a de plus corrigé **3 chiffres factuels** des angles et apporté **3 findings neufs** que les
cinq angles avaient manqués.

## Verdict global

Le chantier est **structurellement sain** (grain des fiches, témoins négatifs, politique de
test) mais **factuellement faux sur le contrat des deux modèles**, et son graphe ne décrit
pas les consommations réelles. Aucune fiche ne descend en `a-faire/` avant la passe de
correction. Le risque dominant, nommé à l'identique par trois angles et le réfuteur : **des
vecteurs plausibles et faux, avec tous les oracles au vert.**

## Les faits qui changent le lot (vérifiés à la source, contre-vérifiés par le réfuteur)

1. **TerraMind small sort du 384-d, pas du 768-d** — le 768 de la carte HF est un
   copier-coller de la variante base ; `forward` rend une **liste** de 12 tenseurs ;
   `merge_method='mean'` moyenne sur l'axe **modalités** (identité en mono-modalité) :
   l'agrégation des patchs est à écrire soi-même (`out[-1].mean(dim=1)`).
2. **TerraMind accepte 256×256** (interpolation des pos-emb) → **256 tokens**. La question
   224/256 est close ; la branche « recadrer à 224 » disparaît des fiches.
3. **Clay masque 75 % des patchs PAR DÉFAUT, y compris en inférence** (`mask_ratio=0.75`,
   `mask_out` inconditionnel, déterministe avec `shuffle=False` : les 3/4 hauts de l'image
   jetés). Le tutoriel officiel pose `mask_ratio=0.0, shuffle=False` explicitement. Sans ces
   deux arguments, tous nos oracles passent au vert sur un embedding faux.
4. **Clay n'attend pas de la réflectance** mais un **z-score sur DN** (mean 1105/std 1809
   pour blue), et son encodeur consomme un **datacube** `{pixels, time[B,4], latlon[B,4],
   gsd, waves}` — 8 dimensions du modèle leur sont réservées. TerraMind pareil côté DN
   (`v1_pretraining_mean ≈ 1390…`). Le port `embed(tensor)` est trop étroit.
5. **L'ordre des bandes Clay** : `nir` en **7ᵉ** position (metadata.yaml), pas en 4ᵉ comme
   dans `BAND_ORDER_10M + BAND_ORDER_20M`. Nuance : Clay est sensor-agnostic — l'invariant
   réel est *pixels/waves/mean/std dans le même ordre*.
6. **La garde HF_HUB_OFFLINE ne couvre pas Clay tel que documenté** (wget d'un .ckpt) et
   Clay télécharge **un second modèle** (teacher timm samvit, 89,7 M params) à la
   construction. Correctif unifiant du réfuteur : passer le ckpt par `hf_hub_download`
   (`made-with-clay/Clay`, licence **apache-2.0** relevée) — une seule garde pour les 3
   artefacts.
7. **Une faute de frappe dans `bands=` de TerraMind produit des poids ALÉATOIRES en
   silence** (pas de else, pas de warning) — et les noms attendus sont `NIR_BROAD`,
   `NIR_NARROW`, `RED_EDGE_1`… : table de correspondance obligatoire, assertion avant build.
8. ⭐ **Finding du réfuteur (K-01 bis)** : la comparaison n'est pas « Clay contre
   TerraMind » mais **« Clay-large contre TerraMind-small »** — ~302 M contre ~21 M de
   paramètres d'encodeur, seul `large` étant publié en v1.5. L'ordre de grandeur du coût
   attendu est **~50×**, pas 4-5×, et la phrase du chapeau « indépendamment du nombre de
   paramètres » disait l'inverse de la réalité. L'asymétrie est subie, pas choisie ; elle se
   déclare et se lit dans les résultats.
9. Divers confirmés : `gsd=20` à passer explicitement (le metadata Clay dit 10) ·
   `metadata.yaml` chargé relativement au CWD · `standardize=True` n'existe pas sur le
   backbone · l'import de claymodel modifie `set_float32_matmul_precision` globalement ·
   claymodel s'installe par `git+` (PEP 508, à trancher en fiche socle) · terratorch tire
   lightning/torchgeo/diffusers… → feature pixi dédiée.

## Les 24 clusters (synthèse — détail dans les rapports d'angle)

| Cluster | Objet | Verdict réfuteur |
|---|---|---|
| K-01 | TerraMind 384-d, forward liste, merge_method | CONFIRMÉ + correction (O5 réécrit : `len(out)==12`, `(1,256,384)`) |
| K-01bis | Clay-large vs TerraMind-small, ~50× | **NEUF (réfuteur)** |
| K-02 | Contrat Clay : masque 75 %, DN z-score, datacube, ordre bandes, doc non exécutable | CONFIRMÉ (5/5) + gsd=20 |
| K-03 | 256 accepté → question 224 close ; 5,2× faux | CONFIRMÉ + correction (ni 5,2 ni 4,0 en l'état : cf. K-01bis) |
| K-04 | Garde poids : Clay hors HF_HUB_OFFLINE, teacher timm, bands= silencieux | CONFIRMÉ + correction (89,7 M, pas 304 M ; hf_hub_download unifie) |
| K-05 | O6 l1-03.2 réécrit les manifestes du Lot 0 en failed | CONFIRMÉ |
| K-06 | Cycle l1-05.3↔l1-04.5 ; critère de sortie n°5 sans porteur | CONFIRMÉ |
| K-07 | Rapports décisionnels dans data/ gitignoré | CONFIRMÉ → docs/lots/lot-1/ |
| K-08 | 8 arêtes manquantes + 2 fausses | CONFIRMÉ + 1 arête de plus (l1-01.2→l1-03.2) ; l1-03.1 → depends_on: [] |
| K-09 | Écritures concurrentes pyproject/pixi.lock/registre/settings ; carte §5.6 fausse | CONFIRMÉ + trou claymodel git+ |
| K-10 | Garde/smoke : propriétaires contradictoires, échappatoire fatale | CONFIRMÉ |
| K-11 | Variante 10 m : O1 mesure 16×, pas 4× ; aucun code ne produit 512² | CONFIRMÉ → 4 forwards 256² synthétiques |
| K-12 | Campagne l1-05.3 ≠ session d'agent | PARTIEL : scission oui ; desserrage 400 chips incompatible avec l1-05.4/O5 sans le relâcher aussi |
| K-13 | Fiche de lot non propagée | PARTIEL : 4/5 (le « critère 3 contredit l1-02.3 » est réfuté) |
| K-14 | Corrélation nuage tronquée : contrôle inopérant par construction | CONFIRMÉ → mesurer sur ingested à 30 % |
| K-15 | Seuils PO en fiche : silhouette sans baseline, dérive sans métrique, fidélité « tient » | CONFIRMÉ (0,2 assumé mais baseline indispensable) |
| K-16 | Témoin l1-05.4/O2 choisi après coup | CONFIRMÉ → nommer les 2 sites maintenant |
| K-17 | Similarité/distance contradictoires | CONFIRMÉ ½ : seule l1-05.2/O3 est fautive ; l1-04.4/O2 était juste |
| K-18 | Déterminisme : O1 jamais rouge, tolérance sans arbitre, threads/torch absents du compagnon | CONFIRMÉ |
| K-19 | Compagnon défini 3 fois ; résumé SCL non spécifié | PARTIEL : vrai mais gravité moindre (site_id et scl_class_counts existent au Lot 0) |
| K-20 | Chemin sans spec_hash → écrasement, réversibilité fausse | CONFIRMÉ → `<model_id>.<spec_hash[:8]>.npy` |
| K-21 | Backfill : O1 impossible (idempotence), O4 SIGINT à vide | CONFIRMÉ |
| K-22 | Import du registre détruit « importable sans torch » | CONFIRMÉ → import paresseux + oracle sys.modules |
| K-23 | Oracles de banc : O5 branche morte, O2 ambigu, O6 sans arrêt, l1-04.3 = L | PARTIEL : 5/6 (anti-cache auto-déclaré : laissé, mineur) |
| K-24 | Mineurs consolidés | CONFIRMÉ sauf E-27 (bornes utiles) et C-28 (CWL non bloquant) |

## « Mesure juste, conclusion fausse » (le mandat du réfuteur)

Six cas attrapés, dont trois qui auraient produit de nouvelles erreurs si on avait appliqué
les corrections des angles telles quelles : remplacer 5,2× par 4,0× en gardant la phrase
« indépendamment du nombre de paramètres » (l'inverse du réel) ; traiter le teacher timm à
304 M (il en fait 89,7) ; appliquer le desserrage de campagne sans relâcher l1-05.4/O5
(rendait la fiche infaisable).

## Plan de correction (ordre du réfuteur, validé par l'orchestrateur)

1. **Fiche socle N0** `l1-00` : dépendances d'inférence (torch, terratorch en feature pixi,
   claymodel @ git+), `models/` gitignoré, `HF_HOME`, fetch-models unifié par
   `hf_hub_download` (3 artefacts), verdict 256 acté. Absorbe K-03, K-04, K-09, socle K-22.
2. **Contrat d'entrée des adapters réécrit** (l1-01.1/01.2/02.1/02.2) : ordre Clay, masque
   0.0, datacube+gsd=20, z-score DN par modèle (la normalisation devient responsabilité
   d'adapter déclarée dans la spec), 384-d, table de noms TerraTorch. Absorbe K-01, K-02.
3. **Graphe** : 9 arêtes ajoutées, 2 retirées, l1-03.1 en N0. Absorbe K-08.
4. **Cycle et porteur du critère n°5** : l1-04.5 après l1-05.3, ratio + confrontation chez
   elle. Absorbe K-06.
5. **Oracles jamais rouges + O6 destructeur** : l1-03.2/O6 (manifeste intouché),
   l1-05.2/O1, l1-03.3/O1+O4, l1-01.2/O5. Absorbe K-05, K-18, K-21, K-23.
   Puis dans la même passe : K-07 (rapports), K-10 (garde/smoke), K-12 (scission campagne),
   K-13 (fiche de lot), K-14 à K-17, K-19, K-20, K-24.

## Points d'arbitrage remontés à Philippe

A. **L'asymétrie Clay-large / TerraMind-small (~50× attendu)** : maintenir les deux modèles
   en la déclarant, ou reconsidérer le duo ? (Recommandation : maintenir — le banc mesurera,
   c'est son travail — mais la phrase fausse du chapeau saute et les paramètres sont publiés
   côte à côte.)
B. **La campagne** : scinder CLI (agent) / campagne complète (fiche humaine), OU
   sous-échantillonner la séparabilité (~400 chips) ET relâcher l'annexe de l1-05.4 à des
   sites nommés. (Recommandation : les deux — CLI agent, campagne humaine ; séparabilité
   d'abord sur sous-échantillon pour confronter l'extrapolation avant de payer le plein
   tarif.)
C. **Seuils décisionnels remontés au cadrage** : silhouette > 0,2 avec baseline triviale
   publiée · rapport de dérive (1−cos, médiane 6 derniers mois) > 2 · plancher de fidélité
   quantif ≥ 0,999 (douteux 0,99–0,999). À acter ou amender.
D. **Arbitrages de dépendances enfouis** : ONNX Runtime (levier quantif, piste 2) — autorisé
   ou interdit ? · matplotlib pour les courbes de trajectoire — ou rendu Pillow ?
   (Recommandation : ONNX autorisé comme mesure jetable hors contrat du paquet ; pas de
   matplotlib, Pillow suffit.)

## Non vérifié par cette revue

Tout ce qui relève de la mesure sur la machine (temps, RAM, drvfs, stabilité bit à bit) — la
revue n'a vérifié que ce que le code source impose, jamais ce qu'il coûte. Le comportement
effectif de HF_HUB_OFFLINE sur timm (à reconfirmer au premier fetch-models réel). L'arbre de
dépendances exact de terratorch/claymodel. Les chiffres du corpus (5 793/9 873/4 959) pris
tels qu'écrits — cohérence interne vérifiée, exactitude non.
