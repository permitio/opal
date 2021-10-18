# Get started with OPAL playground with API source (docker compose)

This tutorial will show you what you can do with OPAL, and teach you about OPAL core features.

We build an example configuration that you can run in **docker compose**. The example was built specifically for you to **explore** OPAL quickly, understand the core features and see what OPAL can do for you.

You can get a running OPAL environment by running one `docker-compose` command.

## Table of Contents
1. [Run the playground and interact with OPAL with API source](#docker-compose-example)
2. [Understand the docker compose example configuration](#compose-recap)

## <a name="docker-compose-example"></a> Run the playground and interact with OPAL with API source
In this section we show how to run OPAL with an example `docker-compose.yml` file. With a few quick commands you can have OPAL up-and-running on your machine and explore the core features. The example configuration is not suitable for production environments (due to the lack of security configuration), but it will help you to understand **why you need OPAL** and how to set an API bundle server as its policy source.



### Step 1: run docker compose to start the opal server and client


You can need to clone the opal repository and run the example compose file from your local clone:
```
git clone https://github.com/authorizon/opal.git
cd opal
docker-compose -f docker/docker-compose-api-policy-source-example.yml up
```

The `docker-compose.yml` we just downloaded ([Click here to view its contents](https://github.com/authorizon/opal/blob/master/docker/docker-compose-api-policy-source-example.yml)) is running 4 containers: Broadcast, OPAL Server, OPAL Client, API bundle server.

We provide a detailed review of exactly **what is running and why** later in this tutorial. You can [jump there by clicking this link](#compose-recap) to gain a deeper understanding, and then come back here, or you can continue with the hands-on tutorial.

OPAL (and also OPA) are now running on your machine, the following ports are exposed on `localhost`:
* OPAL Server (port `:7002`) - the OPAL client (and potentially the cli) can connect to this port.
* OPAL Client (port `:7000`) - the OPAL client has its own API, but it's irrelevant to this tutorial :)
* OPA (port `:8181`) - the port of the OPA agent (running in server mode).
  * OPA is being run by OPAL client in its container as a managed process.
* Nginx server that serve static bundle files (bundle.tar.gz) on port 8000

### <a name="eval-query-opa"></a> Step 2: Send some authorization queries to OPA

As said, OPA REST API is running at port `:8181` and you can issue any requests you'd like.

Let's explore the current state and send some authorization queries to the agent.

The default policy in the [example repo](https://github.com/authorizon/opal-example-policy-repo) is a simple [RBAC](https://en.wikipedia.org/wiki/Role-based_access_control) policy, we can issue this request to get the user's role assignment and metadata:

```
curl --request GET 'http://localhost:8181/v1/data/users' --header 'Content-Type: application/json' | python -m json.tool
```

The expected result is:
```
{
    "result": {
        "alice": {
            "location": {
                "country": "US",
                "ip": "8.8.8.8"
            },
            "roles": [
                "admin"
            ]
        },

        ...
    }
}
```

Cool, let's issue an **authorization** query. In OPA, an authorization query is a query **with input**.

This query asks whether the user `bob` can `read` the `finance` resource (whos id is `id123`):

```
curl -w '\n' --request POST 'http://localhost:8181/v1/data/app/rbac/allow' \
--header 'Content-Type: application/json' \
--data-raw '{"input": {"user": "bob","action": "read","object": "id123","type": "finance"}}'
```

The expected result is `true`, meaning the access is granted:
```
{"result":true}
```

### Step 3: Change the policy, and see it being updated in realtime
Due to the fact the example `docker-compose-api-policy-source-example.yml` makes OPAL track API bundle server that serve the files from `/docker/docker_files/bundle files` to see how a bundle update can affect the policy in realtime, you can run those commands and see the policy update:

```bash
cd docker/docker_files/bundle_files
mv bundle.tar.gz{,.bak1}; mv bundle.tar.gz{.bak,}; mv bundle.tar.gz.bak{1,} # this command replace between the 2 docker files you have there to trigger policy change
# you can now run the same command as before to see that the users data is changed
```

### Step 4: Publish a data update via the OPAL Server
The default policy in the [example repo](https://github.com/authorizon/opal-example-policy-repo) is a simple RBAC policy with a twist.

A user is granted access if:
* One of his/her role has a permission for the requested `action` and `resource type`.
* Only users from the USA can access the resource (location == `US`).

The reason we added the location policy is we want to show you how **pushing an update** via opal with a different "user location" can **immediately affect access**, demonstrating realtime updates needed by most modern applications.

Remember this authorization query?
```
curl -w '\n' --request POST 'http://localhost:8181/v1/data/app/rbac/allow' \
--header 'Content-Type: application/json' \
--data-raw '{"input": {"user": "bob","action": "read","object": "id123","type": "finance"}}'
```

Bob is granted access because the initial `data.json` location is `US` ([link](https://github.com/authorizon/opal-example-policy-repo/blob/master/data.json#L18)):
```
{"result":true}
```

Let's push an update via OPAL and see how poor Bob is denied access.

We can push an update via the opal-client **cli**. Let's install the cli to a new python virtualenv:

```
pyenv virtualenv opaldemo
pyenv activate opaldemo
pip install opal-client
```

Now let's use the cli to push an update to override the user location (we'll come back and explain what we do here in a moment):
```
opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path /users/bob/location
```

We expect to receive this output from the cli:
```
Publishing event:
entries=[DataSourceEntry(url='https://api.country.is/23.54.6.78', config={}, topics=['policy_data'], dst_path='/users/bob/location', save_method='PUT')] reason=''
Event Published Successfully
```

Now let's issue the same authorization query again:
```
curl -w '\n' --request POST 'http://localhost:8181/v1/data/app/rbac/allow' \
--header 'Content-Type: application/json' \
--data-raw '{"input": {"user": "bob","action": "read","object": "id123","type": "finance"}}'
```

And..... no dice. Bob is denied access:
```
{"result":false}
```

Now, what happened when we published our update with the cli? Let's analyze the components of this update.

OPAL data updates are built to support your specific use case.
* You can specify a topic (in the example: `policy_data`) to target only specific opal clients (and by extension specific OPA agents). This is only logical if each microservice you have has an OPA sidecar of its own (and different policy/data needs).
* OPAL specifies **from where** to fetch the data that changed. In this example we used a free and open API (`api.country.is`) that anyone can access. But it can be your specific API, or a 3rd-party.
* OPAL specifies **to where** (destination path) in OPA document hierarchy the data should be saved. In this case we override the `/users/bob/location` document with the fetched data.

## <a name="compose-recap"></a> Let's review together the docker compose example configuration

Our example `docker-compose-api-policy-source-example.yml` ([Click here to view its contents](https://github.com/authorizon/opal/blob/master/docker/docker-compose-api-policy-source-example.yml)) is running 4 containers.

Let's review what they are and their main functions:

#### (1) Postgres
* A PostgresQL database acting as a broadcast channel used to sync between all the instances (worker processes) of **OPAL Server**. If you run only a single worker (not recommended in production) it is not necessary to deploy a broadcast backend.
* These are the currently supported [broadcast backends](https://github.com/encode/broadcaster#available-backends): PostgresQL, Redis, Kafka.

#### (2) OPAL Server
* **Policy-code realtime updates**
  * Tracks a API bundle server and feeds the bundle with .rego and data.json to OPA as policy.
  * If new bundle will be inserted to that server that affects rego or data files, the updated policy will be pushed to OPA automatically in realtime by OPAL.
  * The `docker-compose-api-policy-source-example.yml` file declares a polling interval to check if new commits are pushed to the repo. In production we recommend you setup a webhook from your repo to OPAL server. The only reason we are using polling here is because we want the example `docker-compose-api-policy-source-example.yml` file to work for you as well.
* **Policy-data basic configuration**
  * The OPAL server serves the **base data source configuration** for OPAL client. The configuration is structured as **directives** for the client, each directive specifies **what to fetch** (url), and **where to put it** in OPA data document hierarchy (destination path).
  * The data sources configured on the server will be fetched **by the client** every time it decides it needs to fetch the entire data configuration (e.g: when the client first loads, after a period of disconnection from the server, etc).
  * The data sources specified in the server configuration must always return a complete and up-to-date picture.
  * In our example `docker-compose-api-policy-source-example.yml` file, the server is configured to return these data sources directives to the client:
    * Fetch the `/policy-data` route on the OPAL Server (returns: `{}`) and assign it to the root data document on OPA (i.e: `/`).
* **Policy-data realtime updates**
  * The server can push realtime data updates to the client, it offers a REST API that allows you to push an updates via the server via pub/sub to your OPAL clients (and by extension OPA).
  * We have a guide for that: [how to trigger realtime data updates using OPAL](https://github.com/authorizon/opal/blob/master/docs/HOWTO/trigger_data_updates.md).
  * Example why you need live updates:
    * Alice just invited Bob to a google drive document.
    * Bob expects to be able to view the document immediately.
    * If your authorization layer is implemented with OPA, you cannot wait for the OPA agent to download a new bundle, it's too slow for live application.
    * Instead you push an update via OPAL and the state of the OPA agent changes immediately.

#### (3) OPAL Client
  * **Can run OPA for you (inline process)**
    * The OPAL-Client [docker image](https://hub.docker.com/r/authorizon/opal-client) contains a built-in OPA agent, and can serve as fully-functional **authorization microservice**. OPA is solely responsible for enforcement (evaluates authorization queries) and OPAL is solely responsible for state-management (keeps the policy and data needed to evaluate queries up-to-date).
    * In our example `docker-compose.yml` OPA is enabled and runs on port `:8181`, exposed on the host machine.
    * OPAL will manage the OPA process. If the OPA process fails for some reason (unlikely :)), OPAL will restart OPA and rehydrate the OPA cache with valid and up-to-date state (i.e: will re-download policies and data).
  * **Syncs OPA with latest policy code**
    * Listens to policy code update notifications and downloads up-to-date policy bundles from the server.
  * **Syncs OPA with latest policy data**
    * Listens to policy data update notifications and fetches the data from the sources specified by the directives sent from the server.
    * Can aggregate data from multiple sources: your APIs, DBs, 3rd party SaaS, etc.

#### (4) Nginx (API bundle server)
* An API bundle server that serve static bundle.tar.gz files as the source policy to your OPAL server
* This server takes the configuration from `docker_files` folder to turn off file caching
* This server serve the files inside `docker_files/bundle_files` folder

If you skipped here from step 1, you can now [come back to the hands-on tutorial](#eval-query-opa).

## <a name="troubleshooting"></a> Troubleshooting
You should troubleshoot the same way as shown in the [getting started with containers tutorial](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_using_docker.md#troubleshooting).