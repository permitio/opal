
<p align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=256 alt="opal" border="0" />
</p>
<h1 align="center">
⚡OPAL⚡
</h1>

<h2 align="center">
Open Policy Administration Layer 
</h2>

# 


OPAL adds real-time updates to your fleet of policy agents,
enabling policy enforcement to meet the state-freshness requirements of the application layer.

## 🛠️ Installation 

- As containers 
    
    - server
        ```
        docker pull authorizon/opal-server
        ```

    - client (prebuilt with OPA inside)
        ```
        docker pull authorizon/opal-client
        ```

- As Python packages (python 3.7 >)
    - server
        ```
        pip install opal-server
        python -m opal-server.main
        ```

    - client
        ```
        pip install opal-client
        python -m opal-client.main
        ```

## 📖 Introduction to OPAL - focused data and policy realtime delivery  
Modern applications are complex, distributed, multi-tenant and serve at scale - creating (often) overwhelming authorization challenges. OPA (Open-Policy-Agent) brings the power of decoupled policy to the infrastructure layer (especially K8s), and light applications.OPAL supercharges OPA to meet the pace of live applications, where the picture may change with every user click and api call.

OPAL builds on top of OPA adding realtime updates (via Websocket Pub/Sub) for both policy and data.

OPAL embraces decoupling of policy and code, and doubles down on decoupling policy (GIT driven) and data (distributed data-source fetching engines).



### Problem solved by 

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

<img src="https://i.ibb.co/kGc9nDd/main.png" alt="main" border="0">

OPAL consists of two key components that work together:
1. OPAL Server 
    - Creates a Pub/Sub channel client's subscribe to
    - Tracks a Git repository (via webhook) for updates to policy (or static data)
        - Additional versioned repositories can be supported (e.g. S3, SVN)
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



### Flows
 - Policy 
    - GIT Repo -> OPAL Server -> OPAL Clients -> Policy Agents

 - Data
    - API triggers update -> OPAL Server -> OPAL Clients fetch (new) data from multiple sources -> Policy Agents



## 💡 Key Concepts
### Realtime Pub/Sub updates

### OPAL is stateless
OPAL is designed for scale, mainly via scaling out both client and server instances, as such neither are stateful. state is retained in the end components (the policy agent) and source components (e.g. GIT, databases, API servers)

### OPAL is extendable
OPAL's Pythonic nature makes extending and embedding it extremely easy.
Built with typed Python3, Pydantic, and FastAPI - OPAL is balanced just right for stability and fast development.

We have (and will continue to) put significant effort into OPALs documentation. Each module 

- ## Foundations
    OPAL is built on the shoulders of open-source giants, including:
    - [OpenPolicyAgent](https://www.openpolicyagent.org/)- the default policy agent managed by OPAL.
    - [FastAPI](https://github.com/tiangolo/fastapi) - the ASGI server framework used by OPAL-servers and OPAL-clients.
    - [FastAPI WS PubSub](https://github.com/authorizon/fastapi_websocket_pubsub) - powering the live realtime update channels
    - [Broadcaster](https://pypi.org/project/broadcaster/) allowing syncing server instances through a backend backbone (e.g. Redis, Kafka) 
    

- ## Implementation with Python
    OPAL is written completely in Python3 using FastAPI and Pydantic.
    OPAL was initially created as a component of [**auth**orizon.com](https://www.authorizon.com) , and we've chosen Python for development speed, ease of use and extendability (e.g. Fetcher providers).


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