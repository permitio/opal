# OPAL Architecture


## Components diagram
<img src="https://i.ibb.co/F45Q7bC/main-numbered.png" alt="main-numbered" border="0">

- Legend:
    - Blue line- Data flows 
    - Crimson line -Policy flows
- Components numbered in the diagram
    1. OPAL Server
    2. OPAL Client
    3. OPA (Open Policy Agent)
    4. Application services (The application OPAL powers the authorization layer for)
    5. Data service
    6. GIT repository 
    7. Data sources
    8. OPAL admin 
    9. End users


## Flows
The following text describes common data/policy events in an OPAL system.

- User flows:
    - #### __Authorization queries:__ 
        - Users -> App -> PolicyAgent
        - Users interact with the application triggering authorization queries that the application resolves with the policy agent (directly). The policy agent is constantly kept up-to date by OPAL so it can answer all the queries correctly.

    - #### __Authorization data changes:__ 
        - Users -> App data service -> OPAL-server -> OPAL-clients -> Policy Agents
        - Users (e.g. customers, operators, partners, developers) affect the applications authorization layer (e.g. create new users, assign new roles). Application service triggers an event to OPAL-server, which notifies the clients, which collect the needed data from the affected sources.

- Policy flows
    - #### __Admin updates policy:__ 
        - Admin -> Git -> OPAL-server -> OPAL-clients-> Policy Agents
        - The application admin commits a new version of the application policy (or subset thereof), triggering a webhook to the OPAL-server,which analyzes the new version, creates a differential update and notifies the OPAL-clients of it via Pub/Sub. The OPAL-clients connect back to the OPAL server (via REST) to retrieve the update itself.
    
    - #### __OPAL-server starts :__ 
        - Git -> OPAL-server -> OPAL-clients -> Policy Agents
        - A new OPAL-server node starts, spinning out workers - one worker will be elected as the RepoWatcher. The RepoWatcher worker will retrieve the policy from the repository and share it with the other workers (via the FastAPI Pub/Sub channel) and with other server instances (via the backbone pub/sub [e.g. Kafka, Redis, ...]), and through those to all the currently connected clients (via FastAPI Pub/Sub)
    - #### __OPAL-clients starts :__ 
        - OPAL-server -> OPAL-clients -> Policy Agents
        - The OPAL-client starts and connects to the OPAL-server (via REST) to retrieve it's full policy configuration, caching it directly into the policy-agent.  
        - OPAL-clients keep the policy up to date, by subscribing to policy updates (via FastAPI Pub/Sub) 

- Data flows

    - #### __Application updates authorization data:__ 
        - App Service -> OPAL-server -> OPAL-clients -> Data-Sources -> OPAL-clients -> Policy-Agents
        - Following an a state changing event (e.g. user interaction, API call) The application changes authorization data, and triggers an update event to the OPAL-server (via REST), including a configured data-topic. The OPAL-server will then propagate (via FastAPI Pub/Sub) the event to all OPAL-clients which subscribed to the data-topic.
        Each client (using it's configured Data [FetchProviders](opal/common/fetcher/fetch_provider.py)) will then approach each relevant data-source directly, aggregate the data, and store it in the policy agent.

    - #### __ A third-party updates authorization data:__ 
        - Third-party -> App Data Monitoring Service -> OPAL-server -> OPAL-clients -> Data-Sources -> OPAL-clients -> Policy-Agents
        - A third-party such as a SaaS service updates data relevant for authorization. The Application monitors such changes, and triggers an update event to the OPAL-server (via REST), including a configured data-topic. The OPAL-server will then propagate (via FastAPI Pub/Sub) the event to all OPAL-clients which subscribed to the data-topic.
        Each client (using it's configured Data [FetchProviders](opal/common/fetcher/fetch_provider.py)) will then approach each relevant data-source directly, aggregate the data, and store it in the policy agent.

    - #### __OPAL-server starts :__ 
    - #### __OPAL-client starts :__  
