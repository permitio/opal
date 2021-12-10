<p  align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=170 alt="opal" border="0" />
</p>
<h1 align="center">
⚡OPAL⚡
</h1>

<h2 align="center">
Open Policy Administration Layer
</h2>

<a href="https://github.com/permitio/opal/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/permitio/opal/workflows/Tests/badge.svg" alt="Tests">
</a>
<a href="https://pypi.org/project/opal-server/" target="_blank">
    <img src="https://img.shields.io/pypi/v/opal-server?color=%2331C654&label=OPAL%20Server%20%28PyPi%29" alt="Package">
</a>
<a href="https://pypi.org/project/opal-client/" target="_blank">
    <img src="https://img.shields.io/pypi/v/opal-client?color=%2331C654&label=OPAL%20Client%20%28PyPi%29" alt="Package">
</a>
<a href="https://pepy.tech/project/opal-server" target="_blank">
    <img src="https://static.pepy.tech/personalized-badge/opal-server?period=total&units=international_system&left_color=black&right_color=blue&left_text=Downloads" alt="Downloads">
</a>

<a href="https://hub.docker.com/r/authorizon/opal-server" target="_blank">
    <img src="https://img.shields.io/docker/pulls/authorizon/opal-server?label=Docker%20pulls" alt="Docker pulls">
</a>

<a href="https://opal-access.slack.com/" target="_blank">
    <img src="https://img.shields.io/badge/Slack%20Community-4A154B?logo=slack&logoColor=white" alt="Join our Slack!">
</a>

OPAL is an administration layer for Open Policy Agent (OPA), detecting changes to both policy and policy data in realtime and pushing live updates to your agents.

OPAL brings open-policy up to the speed needed by live applications.
As your application state changes (whether it's via your APIs, DBs, git, S3 or 3rd-party SaaS services), OPAL will make sure your services are always in sync with the authorization data and policy they need (and only those they need).

Check out our main site at <a href="https://opal.ac">OPAL.ac</a> <br/> and this <a href="https://youtu.be/tG8jrdcc7Zo">Microsoft video briefly explaining OPAL and how it works with OPA</a>.

Give us a star ⭐️ - If you are using OPAL or think it is an interesting project, we would love a star ❤️

## Table of contents
 - [Getting Started](#getting-started)
 - [Intro to OPAL](#intro)
    - [Why use OPAL](#why-use-opal)
 - [Architecture](#architecture)
 - [Key Concepts](#key-concepts)
 - [HOW-TOs](#how-tos)
 - [Design Choices](#design)
 - [Join the Community](#community)



## <a name="getting-started"></a>🛠️ Getting started

OPAL is available both as **python packages** with a built-in CLI as well as pre-built **docker images** ready-to-go.

### Getting started with the pre-built docker containers
* [Play with a live playground environment in docker-compose](docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md)
   <!-- - this tutorial is great for learning about OPAL core features and see what OPAL can do for you. -->
* [Try the getting started guide for containers](docs/HOWTO/get_started_with_opal_using_docker.md)
   <!-- - this tutorial will show you how to configure OPAL to your specific needs and run the official docker containers locally or in production. -->
* [Check out the Helm Chart for Kubernetes](https://github.com/permitio/opal-helm-chart)

### Getting started with the python packages and CLI
- Install
    - ```pip install opal-client```
    - ```pip install opal-server```
- Run server (example):
    ```sh
    # Run server
    #  in secure mode -verifying client JWTs (Replace secrets with actual secrets ;-) )
    export OPAL_AUTH_PRIVATE_KEY=~/opal
    export OPAL_AUTH_PUBLIC_KEY=~/opal.pub
    export OPAL_AUTH_MASTER_TOKEN="RANDOM-SECRET-STRING"
    #  Watching a GIT repository from a webhook
    export OPAL_POLICY_REPO_URL=https://github.com/permitio/opal-example-policy-repo.git
    export OPAL_POLICY_REPO_WEBHOOK_SECRET="RANDOM-SECRET-STRING-SHARED-WITH-GITHUB"
    opal-server run
    ```
- Run client (example):
    ```sh
    # Run client
    #  authenticating with a JWT (replace 'JWT-CRYPTOGRAPHIC-CONTENT' with actual token )
    export OPAL_CLIENT_TOKEN="JWT-CRYPTOGRAPHIC-CONTENT"
    # connect to server
    export OPAL_SERVER_URL=https://opal.mydomain.com:7002
    # Subscribe to specific data-topics
    export OPAL_DATA_TOPICS=tenants/my-org,stripe_billing,tickets
    opal-client run
    ```
- ### Try it yourself - [Read the getting started guide](docs/HOWTO/get_started_with_opal.md)

#
## <a name="intro"></a>📖 Introduction to OPAL - data and policy realtime delivery
- Modern applications are complex, distributed, multi-tenant and run at scale - often creating overwhelming authorization challenges. OPA (Open-Policy-Agent) brings the power of decoupled policy to the infrastructure layer (especially K8s), and light applications. OPAL supercharges OPA to meet the pace of live applications, where the state relevant to authorization decisions may change with every user click and api call.

- OPAL builds on top of OPA adding realtime updates (via Websocket Pub/Sub) for both policy and data.

- OPAL embraces decoupling of policy and code, and doubles down on decoupling policy (git driven) and data (distributed data-source fetching engines).

### <a name="why-use-opal"></a> Why use OPAL
- OPAL is the easiest way to keep your solution's authorization layer up-to-date in realtime.
    - OPAL aggregates policy and data from across the field and integrates them seamlessly into the authorization layer.
    - OPAL is microservices and cloud-native (see [key concepts](#key-concepts) below)

### Why OPA + OPAL == 💪 💜
OPA (Open Policy Agent) is great! It decouples policy from code in a highly-performant and elegant way. But the challege of keeping policy agents up-to-date is hard - especially in applications - where each user interaction or API call may affect access-control decisions.
OPAL runs in the background, supercharging policy-agents, keeping them in sync with events in realtime.

### What OPAL *is not*
- A Policy Engine:
    - OPAL uses a policy-engine, but isn't one itself
    - Check out <a href="https://www.openpolicyagent.org/" target="_blank">Open-Policy-Agent</a>, and <a href="https://www.osohq.com/" target="_blank">OSO</a>

- Large scale Global FGA:
    - Currently OPAL is not meant for managing ridiculous (>100GB) amounts of data  within one layer. Though it can complement a CDN to achieve a similar result - [see below](#large-scale-fga).
    - Check out <a href="https://research.google/pubs/pub48190/" target="_blank">Google-Zanzibar</a>

- Fullstack authorization:
    - OPAL and OPA essentially provide microservices for authorization
    - Developers still need to add control interfaces on top (e.g. user-management, api-key-management, audit, impersonation, invites) both as APIs and UIs
    - Check out <a href="https://permit.io" target="_blank">Permit.io</a>


## <a name="architecture"></a>📡  Architecture


<img src="https://i.ibb.co/CvmX8rR/simplified-diagram-highlight.png" alt="simplified" border="0">

See a [more detailed diagram](https://i.ibb.co/kGc9nDd/main.png)
- ### OPAL consists of two key components that work together:
    1. OPAL Server
        - Creates a Pub/Sub channel clients subscribe to
        - Tracks a git repository (via webhook / polling) for updates to policy (or static data)
            - Additional versioned repositories can be supported (e.g. S3, SVN)
        - Accepts data update notifications via Rest API
        - pushes updates to clients (as diffs)
        - scales with other server instances via a configurable backbone pub/sub (Currently supported: Postgres, Redis, Kafka; more options will be added in the future)

    2. OPAL Client
        - Deployed alongside a policy-agent, and keeping it up to date
        - Subscribes to Pub/Sub updates, based on topics for data and policy
        - Downloads data-source configurations from server
            - Fetches data from multiple sources (e.g. DBs, APIs, 3rd party services)
        - Downloads policy from server
        - Keeps policy agents up to date

- ### Further reading
    - [Architecture](docs/architecture.md) deep dive
    - [Code modules](docs/modules.md) review



#


## <a name="key-concepts"></a>💡 Key Concepts
- ### OPAL is realtime (with Pub/Sub updates)
    - OPAL is all about easily managing your authorization layer in realtime.
    - This is achieved by a **Websocket Pub/Sub** channel between OPAL clients and servers.
    - Each OPAL-client (and through it each policy agent) subscribes to and receives updates instantly.
- ### OPAL is stateless
    - OPAL is designed for scale, mainly via scaling out both client and server instances; as such, neither are stateful.
    - State is retained in the end components (i.e: the OPA agent, as an edge cache) and data-sources (e.g. git, databases, API servers)

- ### OPAL is extensible
    - OPAL's Pythonic nature makes extending and embedding new components extremely easy.
    - Built with typed Python3, [pydantic](https://github.com/samuelcolvin/pydantic), and [FastAPI](https://github.com/tiangolo/fastapi) - OPAL is balanced just right for stability and fast development.
    - A key example is OPAL's FetchingEngine and FetchProviders.
    Want to use authorization data from a new source (a SaaS service, a new DB, your own proprietary solution)? Simply [implement a new fetch-provider](docs/HOWTO/write_your_own_fetch_provider.md).
#

## 👩‍🏫 <a name="how-tos"></a> HOW-TOs
- [How to get started with OPAL (Packages and CLI)](docs/HOWTO/get_started_with_opal.md)
- [How to get started with OPAL (Container Images)](docs/HOWTO/get_started_with_opal_using_docker.md)
- [How to trigger Data Updates via OPAL](docs/HOWTO/trigger_data_updates.md)
- [How to extend OPAL to fetch data from your sources with FetchProviders](docs/HOWTO/write_your_own_fetch_provider.md)
- [How to configure OPAL (basic concepts)](docs/HOWTO/configure_opal.md)



## <a name="foundations"></a> 🗿 Foundations
OPAL is built on the shoulders of open-source giants, including:
- [Open Policy Agent](https://www.openpolicyagent.org/)- the default policy agent managed by OPAL.
- [FastAPI](https://github.com/tiangolo/fastapi) - the ASGI API framework used by OPAL-servers and OPAL-clients.
- [FastAPI Websocket PubSub](https://github.com/permitio/fastapi_websocket_pubsub) - powering the live realtime update channels
- [Broadcaster](https://pypi.org/project/broadcaster/) allowing syncing server instances through a backend backbone (e.g. Redis, Kafka)

## <a name="design"></a> 🎨 Design choices

- ### Networking
    - OPAL creates a highly efficient communications channel using [websocket Pub/Sub connections](https://github.com/permitio/fastapi_websocket_pubsub) to subscribe to both data and policy updates. This allows OPAL clients (and the services they support) to be deployed anywhere - in your VPC, at the edge, on-premises, etc.
    - By using **outgoing** websocket connections to establish the Pub/Sub channel most routing/firewall concerns are circumnavigated.
    - Using Websocket connections allows network connections to stay idle most of the time, saving CPU cycles for both clients and servers (especially when comparing to polling-based methods).

- ### Implementation with Python
    - OPAL is written completely in Python3 using asyncio, FastAPI and Pydantic.
    OPAL was initially created as a component of [Permit.io](https://permit.io), and we've chosen Python for development speed, ease of use and extensibility (e.g. fetcher providers).
    - Python3 with coroutines (Asyncio) and FastAPI has presented [significant improvements for Python server performance](https://www.techempower.com/benchmarks/#section=test&runid=7464e520-0dc2-473d-bd34-dbdfd7e85911&hw=ph&test=composite&a=2&f=zik0zj-qmx0qn-zhwum7-zijx1b-z8kflr-zik0zj-zik0zj-zijunz-zik0zj-zik0zj-zik0zj-1kv). While still not on par with Go or Rust - the results match and in some cases even surpass Node.js.

- ### Performance
    - It's important to note that OPAL **doesn't replace** the direct channel to the policy-engine - so for example with OPA all authorization queries are processed directly by OPA's Go based engine.

    - Pub/Sub benchmarks - While we haven't run thorough benchmarks **yet**, we are using OPAL in production - seeing its Pub/Sub channel handle 100s of events per second per server instance with no issue.

- ### Decouple Data from Policy
    - Open Policy Agent sets the stage for [policy code](https://www.openpolicyagent.org/docs/latest/rest-api/#policy-api) and [policy data](https://www.openpolicyagent.org/docs/latest/rest-api/#data-api) decoupling by providing separate APIs to manage each.
    - OPAL takes this approach a step forward by enabling independent update channels for policy code and policy data, mutating the policy agent cache separately.
    - **Policy** (Policy as code): is code, and as such is naturally maintained best within version control (e.g. git). OPAL allows OPA agents to subscribe to the subset of policy that they need directly from source repositories (as part of CI/CD or independently).
    - **Data**: OPAL takes a more distributed approach to authorization data - recognizing that there are **many** potential data sources we'd like to include in the authorization conversation (e.g. billing data, compliance data, usage data, etc etc). OPAL-clients can be configured and extended to aggregate data from any data-source into whichever service needs it.

- ### Decouple data/policy management from policy agents
    - OPAL was built initially with OPA in mind, and OPA is mostly a first-class citizen in OPAL. That said OPAL can support various and multiple policy agents, even in parallel - allowing developers to choose the best policy agent for their needs.

- ### <a name="large-scale-fga"></a> FGA, large scale / global authorization (e.g. Google Zanzibar)
    - OPAL is built for fine grained authorization (FGA), allowing developers to aggregate all and any data they need and restructure it for the authorization layer.
    - OPAL achieves this by making sure each policy-agent is loaded with only the data it needs via topic subscriptions (i.e: data focus and separation).
        - Examples of data separation: the back-office service doesn't need to know about customer users, a tenant specific service doesn't need the user list of other tenants, ...
    - That said OPAL is still limited by OPA's [resource utilization capacity](https://www.openpolicyagent.org/docs/latest/policy-performance/#resource-utilization).
      - If the size of the dataset you need to load into OPA cache is huge (i.e: > 5GB), you may opt to pass this specific dataset by [overloading input](https://www.openpolicyagent.org/docs/latest/external-data/#option-2-overload-input) to your policy.
      - OPAL can still help you if you decide to [shard your dataset](https://en.wikipedia.org/wiki/Shard_(database_architecture)) across multiple OPA agents. Each agent's OPAL-client can subscribe only to the relevant shard.
    - For these larger scale cases, OPAL can potentially become a link between a solution like Google Zanzibar (or equivalent CDN) and local policy-agents, allowing both Google-like scales, low latency, and high performance.
    - If you're developing such a service, or considering such high-scale scenarios; you're welcome to contact us, and we'd be happy to share our plans for OPAL in that area.

- ### Using OPAL for other live update needs
    - While OPAL was created and primarily designed for open-policy and authorization needs; it can be generically applied for other live updates and data/code propagation needs
    - If you'd like to use OPAL or some of its underlying modules for other update cases - please contact us (See below), we'd love to help you do that.

- ### Administration capabilities and UI
    - We've already built policy editors, back-office, frontend-embeddable interfaces, and more as part of [Permit.io](https://permit.io).
    - We have plans to migrate more parts of [Permit.io](https://permit.io) to be open-source; please let us know what you'd like to see next.
# <a name="community"></a>

 ## Joining the community
- We are eager to hear from you 😃
- Raise questions and ask for features to be added to the road-map in our [Github discussions](https://github.com/permitio/opal/discussions)
- Report issues in [Github issues](https://github.com/permitio/opal/issues)
- Chat with us in our [Slack community](https://join.slack.com/t/opal-access/shared_invite/zt-nz6yjgnp-RlP9rtOPwO0n0aH_vLbmBQ)

## Contacting us (the authors)
- We love talking about authorization, open-source, realtime communication, and tech in general.
- Feel free to reach out to us on our [GitHub discussions](https://github.com/permitio/opal/discussions) or directly over [email](mailto:or@permit.io).
## Contributing to OPAL
- Pull requests are welcome! (please make sure to include *passing* tests and docs)
- Prior to submitting a PR - open an issue on GitHub, or make sure your PR addresses an existing issue well.



