# OPAL FAQ
The following is a break down of common questions about OPAL by topics.


# Kubernetes
## If I'm using OPAL just for Kubernetes level authorization, what benefits do I get from using OPAL compared to [kube-mgmt](https://github.com/open-policy-agent/kube-mgmt) ?

OPAL solves the most pain for application-level authorization; where things move a lot faster than the pace of deployments or infrastructure configurations. But it also shines for usage with Kubernetes.  We'll highlight three main points:

1. Decoupling from infrastructure / deployments: With OPAL you can update both policy and data on the fly - without changing the underlying deployment/ or k8s configuration whatsoever (While still using CI/CD and GitOps).
While you can load policies into OPA via kube-mgmt, this practice can become very painful rather quickly when working with complex policies or dynamic policies (i.e. where someone can use a UI or an API to update policies on the fly)
    - OPAL can be very powerful in allowing other players (e.g. customers, product managers, security, etc. ) to affect policies or subsets of them.

2. Data updates and Data distribution- OPAL allows to load data into OPA from multiple sources (including 3rd party services) and maintain their sync.

3. OPAL provides a more secure channel - allowing you to load sensitive data (or data from authorized sources) into OPA.
    - OPAL-Clients authenticate with JWTs - and the OPAL-server can pass them credentials to fetch data from secure sources as part of the update.

    It may be possible to achieve a similar result with K8s Secrets, though there is no current way to do so with kube-mgmt. In addition this would tightly couple (potentially external) services into the k8s configuration.

# Networking

## Can I run the OPAL-server without `OPAL_BROADCAST_URI` ?
Yes, you can potentially choose to run it as a single instance with a single worker  in which case you don’t need the broadcaster channel. The broadcaster, AKA the backbone pub-sub, is used to sync between opal-server instances, one instance doesn't require syncing of course.
This is mainly useful for light-workloads (Where a single worker is enough) and development environments (where you just don't want the hassle of setting up a Kafka / Redis / Postgres service)

# Devops, maintenance and observability

## Does OPAL provide health-check routes ?
Yes both OPAL-server and OPAL-client serve a health check route at `"/healthcheck"`
