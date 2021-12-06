# <a name="intro"></a>💡 Introduction to OPAL - data and policy realtime delivery
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

    </br>
- Large scale Global FGA: 
    - Currently OPAL is not meant for managing ridiculous (>100GB) amounts of data  within one layer. Though it can complement a CDN to achieve a similar result - [see below](#large-scale-fga).
    - Check out <a href="https://research.google/pubs/pub48190/" target="_blank">Google-Zanzibar</a>
        
         </br>
- Fullstack authorization: 
    - OPAL and OPA essentially provide microservices for authorization
    - Developers still need to add control interfaces on top (e.g. user-management, api-key-management, audit, impersonation, invites) both as APIs and UIs 
    - Check out <a href="https://authorizon.com" target="_blank">**auth**orizon</a>


