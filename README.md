
<center><img src="https://i.ibb.co/BGVBmMK/opal.png" height=256 alt="opal" border="0" />

# ⚡OPAL⚡
# Open Policy Administration Layer 
</center>

OPAL adds real-time updates to your fleet of policy agents,
enabling policy enforcement to meet the state-freshness requirements of the application layer.

## 🛠️ Installation 

- As containers (from pre-made images)
    
    - server
        ```
        docker pull authorizon/opal-server
        ```

    - client
        ```
        docker pull authorizon/opal-client
        ```

## 📖 Intro
Modern applications are complex, distributed, multi-tenant and serve at scale - creating (often) overwhelming authorization challenges. OPA (Open-Policy-Agent) brings the power of decoupled policy to the infrastructure layer (especially K8s), and light applications.OPAL supercharges OPA to meet the pace of live applications, where the picture may change with every user click and api call.

OPAL builds on top of OPA adding realtime updates (via Websocket Pub/Sub) for both policy and data 
OPAL embraces decoupling of policy and code, and doubles down on decoupling policy (GIT driven) and data (distributed data-source fetching engines).

### Problem solved by OPAL - focused data and policy realtime delivery  

- Bringing OPA to the application layer (live realtime updates, simplified multi-tenancy, distributed api, multiple data sources (SaaS, dbs, own APIs) ) 
- Realtime API driven updates
- Realtime human driven updates
- differential updates (load only missing delta)
- Live administration and introspection of policy agents and components
- separation and focus - every policy agent gets the data and policy it needs and only those it needs
  - Avoiding crippling data loads 
  - Avoiding over exposure - aka working on a need to know basis (e.g. multi-tenancy )
  - 





## 📡  Architecture
OPAL consists of two key components that work together:
1. OPAL Server 
    - Creates a Pub/Sub channel client's subscribe to
    - Tracks a Git repository (via webhook) for updates to policy (or static data)
    - Accepts data update notifications via Rest API
    - pushes updates to clients (as diffs)
    - scales with other server instances via a configurable backbone pub/sub (Postgre, Redis, Kafka , (more options to be added) )
        
2. OPAL Client - 
    - Deployed alongside a policy-agent keeping it up to date
    - Subscribes to Pub/Sub updates by topics for data and policy 
    - Downloads data source configurations from server
        - Fetches data from multiple sources (DBs, APIs, 3rd party services) 
    - Downloads policy from server
    - Keeps policy agent always up to date

### Diagram
<img src="https://i.ibb.co/5Gdbm0y/main.png" alt="main" border="0">

### Flows
 - Policy 
    - GIT Repo -> OPAL Server -> OPAL Clients -> Policy Agents

 - Data
    - API triggers update -> OPAL Server -> OPAL Clients fetch (new) data from multiple sources -> Policy Agents



## 💡 Key Concepts
### Realtime Pub/Sub updates

Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum

- ## Foundations
    OPAL is built on the shoulders of open-source giants, including:
    - [OpenPolicyAgent](https://www.openpolicyagent.org/)- the default policy agent managed by OPAL.
    - [FAST-API](https://github.com/tiangolo/fastapi) - the ASGI server framework used by OPAL-servers and OPAL-clients.
    - [FAST-API WS PubSub](https://github.com/authorizon/fastapi_websocket_pubsub) - powering the live realtime update channels
    - [broadcaster](https://pypi.org/project/broadcaster/) allowing syncing server instances through a backend backbone (e.g. Redis, Kafka) 
    

- ## Implementation with Python
    OPAL is written completely in Python3 using FastAPI and Pydantic.
    OPAL was initially created as a component of [AUTHorizon.com](https://www.authorizon.com) , and we've chosen Python for development speed, ease of use and extendability (e.g. Fetcher providers).


- ## Decouple data/policy management from policy agents
    OPAL was built initially with OPA in mind, and OPA is mostly a first-class citizen in OPAL. That said OPAL can support various and multiple policy agents, even in parallel - allowing developers to choose the best policy 



### Networking
Using [websocket Pub/Sub connections](https://github.com/authorizon/fastapi_websocket_pubsub) to subscribe to both data and policy updates allows OPAL clients (and the services they support) to be deployed anywhere - in your VPC, at the edge, on-premises, etc.

### Performance
- It's important to note that OPAL *doesn't replace* the direct channel to the policy-engine - so for example with OPA all authorization queries are processed directly by OPA's GO based engine.

- OPAL creates a highly efficient OPAL using fastapi-websocket-pubsub 

Python with Asyncio  

OPAL creates an adjacent  

- Pub/Sub benchmarks - While we haven't run thorough benchmarks yet- we are using OPAL in production- it's Pub/Sub channel handles 100s of events per second with no issue.



### FGA, large scale / global authorization (e.g. Google Zanzibar)
OPAL is built for Fine grained authorizon (FGA)     