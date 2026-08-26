# `tests/fixtures/embed/` — chips gelés pour le smoke d'embedding (l1-01.4)

Quatre acquisitions **réelles**, copiées **octet pour octet** depuis le corpus local
(`D:\datas\tiny-wae\<site_id>\<item_id>\`), pour que le smoke et les tests de chargement de
`l1-01.2` tournent **hors ligne** sans dépendre du corpus complet (16 Gio, hors dépôt).

Fiche source : `docs/backlog/en-cours/l1-01.4.md` (déplacée vers `fait/` une fois recettée).

## Contenu

Chaque sous-dossier `<site_id>_<item_id>/` contient les 3 rasters produits par le pipeline
d'acquisition (Lot 0) et le manifeste **non modifié** :

- `chip.tif` — 512x512, 4 bandes, uint16 (bandes 10 m).
- `chip_20m.tif` — 256x256, 6 bandes, uint16 (bandes 20 m).
- `scl.tif` — 256x256, 1 bande, uint8 (Scene Classification Layer).
- `manifest.json` — copie **identique à l'original** (aucun réécriture, aucun reformatage).

## Fixtures retenues

| Dossier | Site | `item_id` | Date | `cloud_pct` | Rôle |
|---|---|---|---|---|---|
| `A01_S2A_31TGJ_20220911_0_L2A` | A01 | `S2A_31TGJ_20220911_0_L2A` | 2022-09-11 | 0,0 % | cas nominal, très clair |
| `A01_S2A_31TGJ_20221120_0_L2A` | A01 | `S2A_31TGJ_20221120_0_L2A` | 2022-11-20 | 0,0 % | 2e date, même site (déterminisme / idempotence) |
| `C07_S2A_52TEL_20230323_0_L2A` | C07 | `S2A_52TEL_20230323_0_L2A` | 2023-03-23 | 0,0 % | second site, clair |
| `C07_S2B_52TEL_20230226_0_L2A` | C07 | `S2B_52TEL_20230226_0_L2A` | 2023-02-26 | 28,9 % | au-dessus du seuil de filtrage (`l1-03.2`) |

Tous les quatre sont en statut `ingested` (`cloud_pct <= 30` par construction), plateformes
S2A/S2B uniquement — les items S2C (schéma d'assets différent) sont hors sujet ici, la
fixture dédiée est celle du Lot 0.

## Taille

Chaque acquisition pèse environ 2,96 Mo (mesuré : ~2 958 300 à 2 958 430 octets selon
l'item). Le dossier `tests/fixtures/embed/` pèse **11 836 720 octets** (~11,3 Mio /
11,8 Mo), sous le seuil de 15 Mo de l'oracle O1 (voir le Résumé de la fiche `l1-01.4`).

## Comment régénérer

Copie manuelle depuis le corpus local — aucun script n'a été écrit : les acquisitions sont
déjà sur le disque, il n'y a rien à télécharger ni recalculer (cf. la fiche : « s'il suffit
d'une copie manuelle, ne pas écrire de script »).

```bash
# Exemple pour une acquisition (répéter pour les 4 couples site/item_id ci-dessus) :
mkdir -p tests/fixtures/embed/<site_id>_<item_id>
cp -p "/mnt/d/datas/tiny-wae/<site_id>/<item_id>/chip.tif" \
      "/mnt/d/datas/tiny-wae/<site_id>/<item_id>/chip_20m.tif" \
      "/mnt/d/datas/tiny-wae/<site_id>/<item_id>/scl.tif" \
      "/mnt/d/datas/tiny-wae/<site_id>/<item_id>/manifest.json" \
      tests/fixtures/embed/<site_id>_<item_id>/
```

Si le corpus source venait à changer (nouvelle campagne, item renommé), reprendre quatre
acquisitions cochant les mêmes contraintes (voir la fiche `l1-01.4`, section « Contexte et
périmètre ») : au moins un chip `cloud_pct` <= 1 %, un `cloud_pct` strictement > 10 %, deux
sites dont un avec deux dates.

## Hors périmètre

Aucun vecteur d'embedding gelé (impossible de figer 1024 flottants sans figer des poids de
modèle) ; aucune fixture de modèle. La vérification par `load_chip_tensor` appartient à
`l1-01.2` (son oracle O6), pas à cette fixture.
