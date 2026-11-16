# Charging Station Simulator / Simulateur de bornes de recharge

Integration Home Assistant installable via HACS. **Aucun Zigbee, MQTT ni appareil réel n'est utilisé.** Le parking simulé consomme **uniquement** le courant des bornes virtuelles.

## Installation

1. HACS → Dépôts personnalisés → `https://github.com/Taryck/Charging-Station-Simulator` → catégorie **Intégration**.
2. Installer, redémarrer Home Assistant, puis ajouter **Charging Station Simulator** depuis Paramètres → Appareils et services.
3. Configurer le **nombre de bornes** (1–100, défaut 10), les seuils des 3 phases, le multiplicateur d'énergie (défaut ×5), le temps maximum de dépassement (défaut 15 s) et la graine aléatoire.

## Entités générées

- `sensor.ev_sim_total_l1`, `sensor.ev_sim_total_l2`, `sensor.ev_sim_total_l3` : courant général, **somme des bornes**.
- Par borne, exemple 01 : `sensor.ev_sim_borne_01_l1/l2/l3`, `sensor.ev_sim_borne_01_energy`, `sensor.ev_sim_borne_01_status`.
- `number.ev_sim_borne_01_setpoint` : consigne envoyée par le module de pilotage.
- `number.ev_sim_borne_01_starting_current` : intensité de départ **non modifiable pendant une session**.
- `number.ev_sim_borne_01_target_kwh`, `number.ev_sim_borne_01_hardware_min`, `number.ev_sim_borne_01_hardware_max` : paramètres de cycle.
- `select.ev_sim_borne_01_mode` : `tri`, `l1`, `l2`, `l3`; `select.ev_sim_borne_01_command` : `Charging`, `Stopped`, `Paused`.
- `button.ev_sim_borne_01_start` : démarrer une session.
- `select.ev_sim_scenario` et `button.ev_sim_parking_load_scenario` : choisir/exécuter un scénario prédéfini.
- `button.ev_sim_parking_start_all`, `button.ev_sim_parking_stop_all`, `button.ev_sim_parking_reset_trip`.
- `sensor.ev_sim_parking_status` : état du coupe-circuit fictif et attributs `overload_elapsed_s`, `totals_a`, `excess_a`, `limits_a`.

Les identifiants d'entités peuvent recevoir un suffixe si déjà utilisés sur l'instance.

## Fonctionnement

- Pour chaque phase, `total = somme des courants effectivement mesurés de toutes les bornes`, **sans consommation domestique ajoutée**.
- Les bornes sont toutes triphasées capables de fonctionner en `tri` ou en monophasé sur `l1`, `l2` ou `l3`.
- Pour une borne triphasée, chaque phase reçoit un bruit indépendant de ±0,2 A, les valeurs restent liées à la consigne.
- Le courant physique monte/descend de **1 à 2 A/s** en temps réel après changement de consigne, même avec un multiplicateur d'énergie ×20.
- La commande d'arrêt ramène le courant à 0 A en **2 secondes réelles**. À la fin de la quantité d'énergie demandée, la borne s'arrête aussi.
- L'énergie cumulée est calculée à 230 V phase-neutre et avec le multiplicateur de temps : `dE (kWh) = 230 × Σ(Iphase) × secondes_reelles × multiplicateur / 3600000`.
- La borne **refuse** une nouvelle consigne inférieure à son minimum matériel ou supérieure à son maximum matériel, qui peuvent être différents des paramètres dans le module de pilotage.
- Le compteur virtuel suit les bornes et observe la durée du dépassement continu. Au-delà du délai configuré, un coupe-circuit **virtuel** s'ouvre et les recharges s'arrêtent. Réarmement manuel via `button.ev_sim_parking_reset_trip`.
- Le courant de départ d'une session est conservé à part de la consigne courante. Il n'est pas écrasé par les baisses et hausses demandées par le pilotage.

## Scénarios

Choisir `balanced`, `mono_mix`, `overload_two_phases`, `wrong_minimum`, `short_sessions` ou `random`, puis presser **Load Scenario**. Les scénarios ne sont chargés que lorsque toutes les sessions sont terminées ou arrêtées. Le fichier `scenarios/examples.json` documente les cas.

Pour une configuration pilotage avec borne 01 : utiliser les capteurs `sensor.ev_sim_borne_01_l1/l2/l3`, la consigne `number.ev_sim_borne_01_setpoint`, et la commande `select.ev_sim_borne_01_command`, démarrage `Charging`, arrêt `Stopped`. Les courants généraux sont `sensor.ev_sim_total_l1/l2/l3`. **Aucun capteur LiXee physique ne doit être choisi dans la configuration de test.**

## Tests

`python -m pip install pytest && python -m pytest -q tests`

L’intégration et les tests unitaires ne remplacent pas une validation du chargement dans une véritable instance Home Assistant. Les paramètres actuels de simulation ne sont pas persistés après redémarrage : ils sont recréés à partir de la configuration de l'intégration.
## Synchronisation automatique avec Pilotage recharge VE (v0.2.0)

Installer **les deux intégrations** à jour sur la même instance Home Assistant :
- [Charging Station Simulator](https://github.com/Taryck/Charging-Station-Simulator), version 0.2.0 ou supérieure ;
- [Pilotage recharge VE](https://github.com/Taryck/Pilotage-recharge-ve), version 0.2.1 ou supérieure.

Ensuite, ouvrir **Paramètres → Appareils et services → Charging Station Simulator →
Configurer → Synchroniser avec Pilotage recharge VE**.

L'écran présente :
- Le parking et le nombre de bornes ;
- Les entités réelles du **compteur virtuel** L1, L2 et L3 ;
- Le nombre de bornes virtuelles à ajouter et à actualiser.

Cocher la confirmation pour lancer la synchronisation. Il n'y a aucune écriture
dans les fichiers `.storage` : la configuration passe par les API de Home
Assistant, avec une nouvelle entrée de pilotage identifiée comme *simulation*.
Les installations physiques ne sont jamais sélectionnées ni écrasées.

Une nouvelle synchronisation est possible après une modification du nombre de bornes
ou des paramètres du simulateur : les bornes déjà créées sont actualisées en
conservant leur identifiant stable ; les nouvelles sont ajoutées. Aucune borne
absente n'est supprimée automatiquement.

Le régulateur obtient les entités du registre HA, pas des IDs reconstruits :
cela fonctionne même si un utilisateur a renommé ses entités.

**Effet attendu :** l'intégration de pilotage peut agir sur les consignes
virtuelles dès la première synchronisation. Pour éviter une coupure virtuelle
avant même de commencer le test, ajuster d'abord les seuils du simulateur et
la durée de dépassement.

Tests associés : `tests/test_synchronization.py`.


## Énergie cible, tirage aléatoire et fin de charge / Energy targets and taper

Chaque borne possède une cible individuelle en kWh (`number.ev_sim_borne_XX_target_kwh`) et un seuil matériel minimal en ampères (`number.ev_sim_borne_XX_hardware_min`). Le bouton `button.ev_sim_parking_randomize_targets` tire une nouvelle cible aléatoire **entre 5 et 40 kWh** pour chaque borne inactive, sans démarrer de session ni modifier les bornes en charge. Le scénario `random` continue à générer des sessions complètes.

À l'approche de la cible, la borne réduit automatiquement son courant suivant un profil en deux étapes : baisse rapide pendant les 3 premières minutes, puis queue lente sur les 17 minutes suivantes (**20 minutes simulées**, divisées par `time_factor` en temps réel). Le début de réduction est estimé à partir de l'énergie restante et de l'intégrale du profil ; l'arrêt se fait lorsque l'énergie cible est atteinte. La puissance du véhicule ne descend pas sous son minimum matériel avant l'arrêt ; le temps réel nécessaire à la variation physique (1–2 A/s) reste inchangé. En cas de variation de consigne externe ou de cible très faible, la durée réelle de la fin de charge peut différer de 20 minutes. Le profil ne modifie jamais la consigne externe. Les attributs `tapering` et `taper_elapsed_simulated_s` sont visibles sur le capteur d'état de chaque borne.

Each charger has its own target in kWh and its own hardware current minimum in A. Use `button.ev_sim_parking_randomize_targets` to regenerate targets between 5 and 40 kWh for idle chargers without restarting sessions. Near completion, current follows a two-stage taper in simulated time, with an initial fast drop and a slow tail. The external current setpoint is preserved; the hardware minimum remains enforced. Charging ends when the target energy is reached.
