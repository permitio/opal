# OPAL Architecture


## Components diagram
<img src="https://i.ibb.co/F45Q7bC/main-numbered.png" alt="main-numbered" border="0">

- Legend:
    - Blue line: Data flows
    - Purple line: Policy flows
- Components numbered in the diagram
    1. OPAL-Server
        -  The Server managing data and policy; exposing REST routes for clients to retrieve configurations and Pub/Sub channel for clients to subscribe to updates
    2. OPAL-Client
        - The client, running at edge, adjacent to a policy-agent. Subscribes to data and policy updates. Act's on data-updates to approach data sources and aggregate data from them.
        - Clients open an outgoing websocket connection to servers, thus overcoming most firewall / networking challenges, creating a bi-directional Pub/Sub channel.
    3. Open-Policy-Agent (OPA)
        - The policy engine OPAL augments - by default this is OPA
    4. Application services
        - The application OPAL powers the authorization layer for
    5. Data service
        - A service (or multiple services) as part of the application that connect to the OPAL-server to notify of changes to authorization data (guiding OPAL to aggregate data from the relevant data-sources)
    6. GIT repository
        - A versioned store for the authorization policy
        - Triggers a webhook to the OPAL server to notify of policy changes
        - Can potentially be other version controlled stores (e.g. SVN, Perforce, S3)
    7. Data sources
        - Various services (internal and external) that hold and serve data that needs to be used for authorization decisions (by the policy agents)
        - Examples:
            - App REST API service for user list
            - SQL DB storing user roles
            - Billing SaaS service (e.g. Stripe) to
        - OPAL-Clients can be extended with different FetchProviders to allow extraction of data from various sources.
    8. OPAL admins
        - Developers maintaining the application.
        - Can drive new policies in realtime by simply pushing to their version control (Can simply be the same repository used by CI/CD for the whole app)
        - Can configure and control OPAL clients and their associated policy-agents from a unified control plane
        - Can change the applications data and easily sync authorization to match it.

    9. End users
        - The users of the application, enjoying a seamless experience - working each within their authorization bounds (enforced by open-policy-agents) - e.g. user permissions, roles, tenants.
        - Through OPAL the application's authorization layer adjusts to their needs in realtime - a new user invited can access instantly; new permissions assigned take affect at once. No waiting, no redeployments.
        - Thanks to OPA all requests are processed for authorization in record-breaking speed.


- ## Lightweight Pub/Sub and Backbone Pub/Sub
    - OPAL's architecture potentially uses two Pub/Sub channels-
        1. Client <> Server - lightweight websocket Pub/Sub
        2. Server <> Server - backbone Pub/Sub

        While the lightweight channel requires no additional infrastructure, and can suffice for the can we are running only a single OPAL-server. If we wish to scale-out OPAL-servers, we achieve this using a backbone Pub/Sub (such as Redis, Kafka, or Postgres Listen/Notify) to sync all the servers (So a client connecting to one server, receive notifications of updates that are triggered by another server)
        The backbone Pub/Sub is connected to the lightweight Pub/SUb through the [Broadcaster](https://pypi.org/project/broadcaster/) module.


- ## Communication flows
    The following text describes common data/policy events/scenarios in an OPAL system.

    - User flows:
        - Flows triggered by
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
            - A new OPAL-server node starts, spinning out workers - one worker will be elected as the GitPolicySource. The GitPolicySource worker will retrieve the policy from the repository and share it with the other workers (via the FastAPI Pub/Sub channel) and with other server instances (via the backbone pub/sub [e.g. Kafka, Redis, ...]), and through those to all the currently connected clients (via FastAPI Pub/Sub)
        - #### __OPAL-clients starts :__
            - OPAL-server -> OPAL-clients -> Policy Agents
            - The OPAL-client starts and connects to the OPAL-server (via REST) to retrieve it's full policy configuration, caching it directly into the policy-agent.
            - OPAL-clients keep the policy up to date, by subscribing to policy updates (via FastAPI Pub/Sub)

    - Data flows

        - #### __Application updates authorization data:__
            - App Service -> OPAL-server -> OPAL-clients -> Data-Sources -> OPAL-clients -> Policy-Agents
            - Following an a state changing event (e.g. user interaction, API call) The application changes authorization data, and triggers an update event to the OPAL-server (via REST), including a configured data-topic. The OPAL-server will then propagate (via FastAPI Pub/Sub) the event to all OPAL-clients which subscribed to the data-topic.
            Each client (using it's configured Data [FetchProviders](opal/common/fetcher/fetch_provider.py)) will then approach each relevant data-source directly, aggregate the data, and store it in the policy agent.

        - #### __A third-party updates authorization data:__
            - Third-party -> App Data Monitoring Service -> OPAL-server -> OPAL-clients -> Data-Sources -> OPAL-clients -> Policy-Agents
            - A third-party such as a SaaS service updates data relevant for authorization. The Application monitors such changes, and triggers an update event to the OPAL-server (via REST), including a configured data-topic. The OPAL-server will then propagate (via FastAPI Pub/Sub) the event to all OPAL-clients which subscribed to the data-topic.
            Each client (using it's configured Data [FetchProviders](opal/common/fetcher/fetch_provider.py)) will then approach each relevant data-source directly, aggregate the data, and store it in the policy agent.

        - #### __OPAL-client starts :__
            - OPAL-server -> OPAL-clients -> Data-Sources -> OPAL-clients -> Policy-Agents
            - OPAL-client connects to OPAL-server (via REST) to download base data-source configuration (for its configured topics); and then using it's configured Data [FetchProviders](opal/common/fetcher/fetch_provider.py)) will approach each relevant data-source directly, aggregate the data, and store it in the policy agent.