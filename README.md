
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
<a href="https://github.com/authorizon/opal/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/authorizon/opal/workflows/Tests/badge.svg" alt="Tests">
</a>

# 
OPAL is an administration layer for Open Policy Agent (OPA), detecting changes to both policy and data and pushing live updates to your agents.

OPAL brings open-policy up to the speed needed by live applications.
As you push updates to your application's stores (e.g. Git, DBs, S3, SaaS services) OPAL will make sure your services are always in sync with the authorization data and policy they need (and only those they need.) 
## 🛠️ Installation 

- As containers 
    
    - Server
        ```
        docker pull authorizon/opal-server
        ```
        ```
        docker run authorizon/opal-server
        ```

    - Client (prebuilt with OPA inside)
        ```
        docker pull authorizon/opal-client
        ```
        ```
        docker run authorizon/opal-client
        ```

- Or [install as directly as Python packages (python >3.7 )](docs/HOWTO/install_as_python_packages.md) 
    - ```pip install opal-client``` 
    - ```pip install opal-server``` 

#

## 📖 Introduction to OPAL - data and policy realtime delivery  
- Modern applications are complex, distributed, multi-tenant and serve at scale - creating (often) overwhelming authorization challenges. OPA (Open-Policy-Agent) brings the power of decoupled policy to the infrastructure layer (especially K8s), and light applications.OPAL supercharges OPA to meet the pace of live applications, where the picture may change with every user click and api call.

- OPAL builds on top of OPA adding realtime updates (via Websocket Pub/Sub) for both policy and data.

- OPAL embraces decoupling of policy and code, and doubles down on decoupling policy (Git driven) and data (distributed data-source fetching engines).




## 📡  Architecture


<img src="https://i.ibb.co/YD8phRD/simplified-diagram-highlight.png" alt="simplified" border="0">

See a [More detailed diagram](<img src="https://i.ibb.co/kGc9nDd/main.png" alt="main" border="0">)
- ### OPAL consists of two key components that work together:
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
        - Keeps policy agents up to date

- ### Further reading
    - [Architecture](docs/architecture.md) deep dive
    - [Code modules](docs/modules.md) review



#


## 💡 Key Concepts
- ### OPAL is realtime (with Pub/Sub updates)
    - OPAL is all about easily managing your authorization layer in realtime.
    - This is achieved by a **Websocket Pub/Sub** channel between OPAL clients and servers.
    - Each OPAL-client (and through it each policy agent) subscribes to and receives updates instantly 
- ### OPAL is stateless
    - OPAL is designed for scale, mainly via scaling out both client and server instances, as such neither are stateful. 
    - State is retained in the end components (the policy agent) and source components (e.g. GIT, databases, API servers)

- ### OPAL is extendable
    - OPAL's Pythonic nature makes extending and embedding it extremely easy.
    - Built with typed Python3, Pydantic, and FastAPI - OPAL is balanced just right for stability and fast development.
    - A key example is OPAL's FetchingEngine and FetchProviders.
    Want to use authorization data from a new source (a SaaS service, a new DB, your own proprietary solution)? Simply [implement a new fetch-provider](docs/HOWTO/write_your_own_fetch_provider.md) 
#

- ## HOW-TOs
    - How to extend OPAL to fetch data from your sources with [FetchProviders](docs/HOWTO/write_your_own_fetch_provider.md)



- ## Foundations
    OPAL is built on the shoulders of open-source giants, including:
    - [OpenPolicyAgent](https://www.openpolicyagent.org/)- the default policy agent managed by OPAL.
    - [FastAPI](https://github.com/tiangolo/fastapi) - the ASGI server framework used by OPAL-servers and OPAL-clients.
    - [FastAPI WS PubSub](https://github.com/authorizon/fastapi_websocket_pubsub) - powering the live realtime update channels
    - [Broadcaster](https://pypi.org/project/broadcaster/) allowing syncing server instances through a backend backbone (e.g. Redis, Kafka) 
    
## 🎨 Design choices

- ## Networking
    - OPAL creates a highly efficient communications channel Using [websocket Pub/Sub connections](https://github.com/authorizon/fastapi_websocket_pubsub) to subscribe to both data and policy updates allows OPAL clients (and the services they support) to be deployed anywhere - in your VPC, at the edge, on-premises, etc.
    - By using  outgoing websocket connections to establish the Pub/Sub channel most routing/firewall concerns are circumnavigated
    - Using Websocket connections allows network connections to be dormant most fo the time (saving CPU cycles for both clients and servers) - especially when comparing to polling based methods.

- ## Implementation with Python
    - OPAL is written completely in Python3 using FastAPI and Pydantic.
    OPAL was initially created as a component of [**auth**orizon.com](https://www.authorizon.com), and we've chosen Python for development speed, ease of use and extendability (e.g. Fetcher providers).
    - Python3 with coroutines (Asyncio) and FastAPI has presented [significant improvements for Python server performance](https://www.techempower.com/benchmarks/#section=test&runid=7464e520-0dc2-473d-bd34-dbdfd7e85911&hw=ph&test=composite&a=2&f=zik0zj-qmx0qn-zhwum7-zijx1b-z8kflr-zik0zj-zik0zj-zijunz-zik0zj-zik0zj-zik0zj-1kv). While still not on par with GO or Rust - the results match and in some cases even surpass NodeJS.

- ## Performance
    - It's important to note that OPAL *doesn't replace* the direct channel to the policy-engine - so for example with OPA all authorization queries are processed directly by OPA's GO based engine.

    - Pub/Sub benchmarks - While we haven't run thorough benchmarks **yet**- we are using OPAL in production- seeing its Pub/Sub channel handle 100s of events per second per server instance with no issue.

- ## Decouple Data from Policy 
    - Open-Policy-Agent sets the stage for authorization-data and policy decoupling by providing a separate API to manage each. 
    - OPAL takes this approach a step forward by enabling independent update channels for each into the policy cache.
    - POLICY - Policy as code - is code, and as such is naturally maintained best within version control (e.g. GIT). OPAL allows open-policy agents to get the subset of policy they need directly from repositories (as part of CI/CD or independently)
    - DATA - OPAL takes a more distributed approach to authorization data - recognizing that there are many potential data sources we'd like to include in the authorization conversion (e.g. billing data, compliance data, usage data, etc. etc. ). OPAL-clients can be configured and extended to aggregate any data-source into whichever service needs it.

- ## Decouple data/policy management from policy agents
    - OPAL was built initially with OPA in mind, and OPA is mostly a first-class citizen in OPAL. That said OPAL can support various and multiple policy agents, even in parallel - allowing developers to choose the best policy and agent for their needs.

- ## FGA, large scale / global authorization (e.g. Google Zanzibar)
    - OPAL is built for fine grained authorizon (FGA), allowing developers to aggregate all and any the data they need and restructure it for the authorization layer     
    - By making sure each policy-agent is loaded with only the data it needs (via topic subscriptions) - i.e. data focus and separation.
        - examples of data-separation: the back-office service doesn't need to know about customer users, a tenant specific service doesn't need the user list of other tenants, ...
    - That said OPAL with OPA as it is - is still limited in capacity of authorization data that can be available per policy decision; but after applying said data focus this will only impact applications with truly insane scales (where the data for every decision is larger than ~5GB). 
    - For these larger scale cases, OPAL can potentially become a link between a solution like Google Zanzibar (or equivalent CDN) and local policy-agents. (Allowing both Google like scales, low latency, and high performance)
    - I you're developing such a service, or considering such high-scale scenarios; you're welcome to contact us, we'd be happy to share our plans for OPAL in that area.

- ## Using OPAL for other live update needs
    - While OPAL was created and primarily designed for open-policy and authorization needs; it can be generically applied for other live updates and data/code propagation needs
    - If you'd like to use OPAL or some of its underlying modules for other update cases - please contact us (See below), we'd love to help you do that.

- ## Administration capabilities and UI
    - We've already built policy editors, back-office, frontend-embeddable interfaces, and more as part of [**auth**orizon.com](https://www.authorizon.com)
    - We have plans to migrate more parts of [**auth**orizon.com](https://www.authorizon.com) to be open-source; please let us know what you'd like to see next
#

 - ## Joining the community 
    - We are eager to hear from you 😃 
    - Raise questions and ask for features to be added to the road-map in our [Github discussions](https://github.com/authorizon/opal/discussions)
    - Report issues in [Github issues](https://github.com/authorizon/opal/issues)
    - Chat with us in our [Slack community](https://join.slack.com/t/opal-access/shared_invite/zt-nz6yjgnp-RlP9rtOPwO0n0aH_vLbmBQ)

- ## Contacting us (the authors)
    - We love talking about authorization, open-source, realtime communication, and tech in general
    - feel free to reach out to us on our [GitHub discussions](https://github.com/authorizon/opal/discussions) or directly over [email](mailto:or@authorizon.com)
- ## Contributing to OPAL
    - Pull requests are welcome! (please make sure to include *passing* tests and docs)
    - Prior to submitting a PR - open an issue on GitHub, or make sure your PR addresses an existing issue well.   
    
    
    