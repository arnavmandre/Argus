# UrbanTwin AI — Data Schema Documentation

This document describes the structure and parameter specifications for `city.json` and `citizens.json`, which form the foundational data layer for the UrbanTwin AI simulation model.

---

## 1. `city.json` Schema

The `city.json` file defines the urban topology, including environmental zones, physical structures (buildings), and pedestrian transit links (routes).

### Top-Level Attributes

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | Integer | Yes | Schema revision identifier (e.g., `1`). |
| `description` | String | No | High-level summary of the city dataset. |
| `fields` | Object | No | Metadata dict detailing parameter definitions. |
| `zones` | Array[Object] | Yes | List of spatial zones within the city. |
| `buildings` | Array[Object] | Yes | List of structural entities within zones. |
| `routes` | Array[Object] | Yes | List of directional or bi-directional pathways between buildings. |

---

### Object Definitions

#### A. `zones` Array Elements
Zones represent distinct geographical or planning areas with common microclimate or infrastructural traits.

* **`id`** (`String`, Required): Unique identifier for the zone (e.g., `"Zone A"`). Referenced by buildings and route paths.
* **`drainage`** (`Float`, Range: `0.0`–`1.0`): Heuristic score for stormwater management capability.
  * `0.0`: Poor drainage (highly prone to flash flooding and standing water).
  * `1.0`: Excellent drainage infrastructure.
* **`shade`** (`Float`, Range: `0.0`–`1.0`): Level of canopy cover or solar protection across the zone.
  * `0.0`: Exposed, unshaded area.
  * `1.0`: Fully shaded / covered environment.

#### B. `buildings` Array Elements
Buildings serve as origin/destination nodes for simulated agents and experience localized environmental conditions.

* **`id`** (`String`, Required): Unique building identifier (e.g., `"H1"`, `"W1"`).
* **`name`** (`String`, Required): Human-readable display label (e.g., `"Riverside Homes"`).
* **`type`** (`String`, Required): Functional classification of the facility. Common categories: `residential`, `transit_hub`, `office`, `school`, `hospital`, `market`.
* **`zone`** (`String`, Required): Foreign key corresponding to a `zones.id` entry.
* **`capacity`** (`Integer`, Range: $\ge 0$): Maximum peak-window throughput/absorption capacity of the building's entrances or immediate concourse.
  * `0`: Typical for standard residential origins that do not receive destination traffic.
* **`cooling`** (`Float`, Range: `0.0`–`1.0`): Climate control and heat refuge factor inside or immediately around the facility.
  * `0.0`: No climate control / exterior exposure.
  * `1.0`: Fully air-conditioned / climate-controlled refuge.
* **`flood_exposure`** (`Float`, Range: `0.0`–`1.0`): Vulnerability to ground-level water accumulation based on structural elevation and positioning.
  * `0.0`: Elevated / fully protected against water intrusion.
  * `1.0`: At-grade or submerged ground floor directly on a surface flow path.

#### C. `routes` Array Elements
Routes define pedestrian pathways connecting pairs of buildings.

* **`id`** (`String`, Required): Unique route identifier (e.g., `"R1"`).
* **`start`** (`String`, Required): Foreign key corresponding to a `buildings.id` entry (Origin/Endpoint A).
* **`end`** (`String`, Required): Foreign key corresponding to a `buildings.id` entry (Destination/Endpoint B).
* **`distance_km`** (`Float`, Range: $> 0.0$): Physical distance of the path in kilometers.
* **`shade`** (`Float`, Range: `0.0`–`1.0`): Average solar cover along the length of the path.
* **`drainage`** (`Float`, Range: `0.0`–`1.0`): Path-level surface water runoff performance.
* **`base_crowding`** (`Float`, Range: `0.0`–`1.0`): *Ambient* congestion — how busy the corridor is from traffic the simulation does not model. It is a floor, not the reported crowding: actual congestion is computed from how many simulated pedestrians choose the route.
* **`transit`** (`Float`, Range: `0.0`–`1.0`, Optional, Default: `0.0`): Level of public transport support or integration along the route corridor.
* **`capacity_pph`** (`Float`, Range: $> 0.0$, Optional, Default: `1500`): Pedestrians per hour the corridor absorbs before it reads as fully congested. Denominator of the emergent crowding calculation.
* **`greenery`** (`Float`, Range: `0.0`–`1.0`, Optional, Defaults to `shade`): Trees and planting. Distinct from `shade` — an arcade shades without being green — and it is `greenery`, not `shade`, that `green_preference` responds to.
* **`via_zones`** (`Array[String]`, Optional): List of `zones.id` values through which the pathway travels.

---

## 2. `citizens.json` Schema

The `citizens.json` file defines synthetic pedestrian agents that navigate the urban graph based on personal tolerances and preferences.

### Top-Level Attributes

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | Integer | Yes | Schema revision identifier (e.g., `1`). |
| `description` | String | No | Dataset notes and simulation guidance. |
| `fields` | Object | No | Key-value legend explaining property constraints. |
| `citizens` | Array[Object] | Yes | Collection of synthetic agent objects. |

---

### Object Definitions (`citizens` Array Elements)

Each object represents a single agent (or a weighted group of agents) navigating from a home location to a destination.

#### Identity & Spatial Anchors
* **`id`** (`String`, Required): Unique agent identifier (e.g., `"C001"`).
* **`archetype`** (`String`, Required): Demographic or behavioral label used for categorization/reporting (e.g., `"Student"`, `"Outdoor worker"`, `"Elderly citizen"`).
* **`home`** (`String`, Required): Foreign key pointing to a `buildings.id` representing origin location.
* **`destination`** (`String`, Required): Foreign key pointing to a `buildings.id` representing target trip destination. *(Note: At least one route in `city.json` must exist between `home` and `destination`)*.

#### Physical Capabilities & Weights
* **`walking_speed_kmh`** (`Float`, Range: $> 0.0$): Walking speed in kilometers per hour (typically `2.0`–`5.5`). Sets travel time, and because heat/rain/crowd exposure accumulates per hour of travel, a slower walker on the same route absorbs more stress.
* **`weight`** (`Float`, Range: $> 0.0$, Optional, Default: `1.0`): Representation factor indicating the relative share of total population this single sample agent represents.

#### Behavioral Parameters (Tolerance & Preference)
All tolerances and preferences are normalized heuristic indicators bounded between `0.0` and `1.0`.

* **`heat_tolerance`** (`Float`, Range: `0.0`–`1.0`): Resiliency to high temperature and ambient heat stress.
  * `0.0`: Extremely heat-sensitive (incurs high route cost/discomfort under heat).
  * `1.0`: High heat tolerance (e.g., outdoor laborers).
* **`rain_tolerance`** (`Float`, Range: `0.0`–`1.0`): Ability/willingness to traverse wet or poorly drained pathways during rain events.
  * `0.0`: High sensitivity to precipitation and flooding.
  * `1.0`: Highly resilient to rainfall.
* **`crowd_tolerance`** (`Float`, Range: `0.0`–`1.0`): Tolerance toward high pedestrian traffic and congestion along routes and building choke-points.
  * `0.0`: Strong aversion to crowded corridors.
  * `1.0`: Indifferent to dense crowding.
* **`green_preference`** (`Float`, Range: `0.0`–`1.0`): Willingness to take longer or alternative paths to travel through shaded/green corridors.
* **`transit_preference`** (`Float`, Range: `0.0`–`1.0`): Affinity for choosing paths with dedicated public transit infrastructure (`transit > 0`).
* **`accessibility_need`** (`Float`, Range: `0.0`–`1.0`, Optional / Legacy): Historical demographic parameter representing mobility or physical accessibility requirements. *(Note: Ignored by current version logic)*.
---

## 3. `urbantwin_demo_output.json` — headline metrics

Written by `python main.py`. Two full snapshots (`before`, `after`) plus the
advisor, the applied intervention, the deltas, and a `control` run.

All metrics are `0`–`100` heuristic prototypes, not measurements. The
visualisation layer consumes **canonical v1 snapshots** (see
`docs/INTEGRATION_CONTRACT.md`), not this file directly — the exporter owns
normalising these to `0`–`1`.

* **`heat_stress`**, **`rain_impact`** — city-level environmental readings after
  any intervention is applied.
* **`crowding`** — blend of corridor congestion (70%) and building-entrance
  crowding (30%). Corridor congestion is **emergent**: it comes from how many
  simulated pedestrians actually chose each route, against `capacity_pph`, not
  from the population slider.
* **`safety`**, **`mobility`**, **`comfort`** — city-average pillars derived
  from the three readings above. Higher is better.
* **`citizen_comfort`** — population-weighted mean of what the simulated
  citizens actually experienced on the routes they each chose. This is the
  human-centric metric: it moves when citizen tolerances or walking speeds
  change, where the city-average pillars do not. Note it is a *different
  quantity* from `comfort` above, and is usually higher, because citizens
  choose protective routes.
* **`mean_travel_minutes`** — population-weighted mean trip time. The only
  metric not bounded to `0`–`100`.
* **`human_experience_index`** — weighted average of four bounded pillars:
  `citizen_comfort` 0.35, `comfort` 0.25, `safety` 0.20, `mobility` 0.20.
  Weights sum to 1.0, so the index stays within `0`–`100` by construction.

Per-citizen rows additionally carry `travel_minutes`, `route`, exposure values
and `comfort`. Per-route rows carry `crowding`, `chosen_by_agents`,
`peak_pedestrians`, `capacity_pph`, `utilisation`, `shade` and `greenery`.
