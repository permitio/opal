# Get started with OPAL docker containers

This tutorial will teach you how to run OPAL using the official docker images.

We also have another tutorial for [running OPAL with an example docker-compose configuration](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md). This other tutorial is better for **learning** about OPAL in a **live playground environment**.

<table>
  <tbody>
    <tr>
      <td valign="top" align="left">Use <strong>this</strong> tutorial if you</td>
      <td valign="top" align="left">
        <ul>
          <li>Understand what OPAL is for (main features, how it works).</li>
          <li>Want to <strong>run</strong> OPAL with a real configuration.</li>
          <li>Want a step-by-step guide for deploying in production.</li>
        </ul>
      </td>
    </tr>
    <tr>
      <td valign="top" align="left">Use the <a href="https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md">other</a> tutorial if you</td>
      <td valign="top" align="left">
        <ul>
          <li>Want to <strong>explore</strong> OPAL quickly.</li>
          <li>Get a working playground with <strong>one</strong> <code>docker-compose</code> command.</li>
          <li>Want to <strong>learn</strong> about OPAL core features and see what OPAL can do for you.</li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

Our recommendation is to start with the [docker-compose playground](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md) (quicker setup, better as a first tutorial) and then come back here and learn how to setup OPAL with a real configuration.

## Table of Content
- [Download OPAL images from Docker Hub](#download-images)
- [Before you begin](#before-you-begin)
- [How to run OPAL Server](#run-server)
- [How to run OPAL Client](#run-client)
- [How to push data updates from an authoritative source](#push-updates)
- [Troubleshooting](#troubleshooting)

## <a name="download-images"></a> How to get the OPAL images from Docker Hub

<table>
  <tbody>
    <tr>
      <th align="left">Image Name</th>
      <th align="left" width="45%">How to Download</th>
      <th align="left" width="45%">Description</th>
    </tr>
    <tr>
      <td valign="top"><a href="https://hub.docker.com/r/authorizon/opal-server">OPAL Server</a></td>
      <td valign="top"><code>docker pull authorizon/opal-server</code></td>
      <td valign="top">
      <ul>
        <li>Creates a Pub/Sub channel clients subscribe to</li>
        <li>Tracks a git repository (via webhook / polling) for updates to policy and static data</li>
        <li>Accepts data update notifications via Rest API</li>
        <li>Serves default data source configuration for clients</li>
        <li>Pushes policy and data updates to clients</li>
      </ul>
      </td>
    </tr>
    <tr>
      <td valign="top"><a href="https://hub.docker.com/r/authorizon/opal-client">OPAL Client</a></td>
      <td valign="top"><code>docker pull authorizon/opal-client</code></td>
      <td valign="top">
      <ul>
        <li>Prebuilt with an OPA agent inside the image</li>
        <li>Keeps the OPA agent cache up to date with realtime updates pushed from the server</li>
        <li>Can selectively subscribe to specific topics of policy code (rego) and policy data</li>
        <li>Fetches data from multiple sources (e.g. DBs, APIs, 3rd party services)</li>
      </ul>
      </td>
    </tr>
    <tr>
      <td valign="top"><a href="https://hub.docker.com/r/authorizon/opal-client">OPAL Client (Standalone)</a></td>
      <td valign="top"><code>docker pull authorizon/opal-client-standalone</code></td>
      <td valign="top">
      <ul>
        <li><strong>Same as OPAL Client, you want only one of them</strong></li>
        <li>This image does not come with OPA installed</li>
        <li>Intended to be used when you prefer to deploy OPA separately in its own container</li>
      </ul>
      </td>
    </tr>
  </tbody>
</table>

## <a name="before-you-begin"></a> Before you begin

### <a name="running-docker"></a> Running docker containers
Since running OPAL is simply spinning docker containers, OPAL is cloud-ready and can fit in many environments: AWS (ECS, EKS, etc), Google Cloud, Azure, Kubernetes, etc.

Each environment has different instructions on how to run container-based applications, and as such, environment-specific instructions are outside the scope of this tutorial. We will show you how to run the container locally with `docker run`, and you can then apply the necessary changes to your runtime environment.

#### Example production setup
We at [**auth**orizon](https://authorizon.com) currently run our OPAL production cluster using the following services:
* AWS ECS Fargate - for container runtime.
* AWS Secrets Manager - to store sensitive OPAL config vars.
* AWS Certificate Manager - for HTTPS certificates.
* AWS ELB - for load balancer.

#### <a name="example-docker-run"></a> Example docker run command
Example docker run command (no worries, we will show real commands later):
```
docker run -it \
  -v ~/.ssh:/root/ssh \
  -e "OPAL_AUTH_PRIVATE_KEY=$(OPAL_AUTH_PRIVATE_KEY)" \
  -e "OPAL_AUTH_PUBLIC_KEY=$(OPAL_AUTH_PUBLIC_KEY)" \
  -e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
  -p 7002:7002 \
  authorizon/opal-server
```
This command | In production environments
:--- | :---
Runs the docker container in interactive mode | Typically no such option
Mounts the `~/.ssh` dir as volume | Varies between environment, e.g in AWS ECS you would mount volumes via the task definition.
Passes the following env vars to the docker container as config: `OPAL_AUTH_PRIVATE_KEY`, `OPAL_AUTH_PUBLIC_KEY`, `OPAL_POLICY_REPO_URL`. | Varies between environment, e.g in AWS ECS you would specify env vars values via the task definition.
Exposes port 7002 on the host machine. | Varies between environment, e.g in AWS ECS you would specify exposed ports in the task definition, and will have to expose these ports via a load balancer.

### <a name="configuration"></a> Configuration Variables
We will now explain how to pass configuration variables to OPAL.

* In its dockerized form, OPAL server and client containers pick up their configuration variables from **environment variables** prefixed with `OPAL_` (e.g: `OPAL_DATA_CONFIG_SOURCES`, `OPAL_POLICY_REPO_URL`, etc).
* The OPAL CLI can pick up config vars from either **environment variables** prefixed with `OPAL_` or from **CLI arguments** (interchangable).
  * Supported CLI options are listed in `--help`.
  * Each cli argument can match to a **corresponding** environment variable:
    * Simply convert the cli argument name to [SCREAMING_SNAKE_CASE](https://en.wikipedia.org/wiki/Naming_convention_(programming)#Multiple-word_identifiers), and prefix it with `OPAL_`.
    * Examples:
      * `--server-url` becomes `OPAL_SERVER_URL`
      * `--data-config-sources` becomes `OPAL_DATA_CONFIG_SOURCES`

### <a name="security-considerations"></a> Security Considerations (for production environments)
You should read and understand [OPAL Security Model](https://github.com/authorizon/opal/blob/master/docs/security.md) before going to production.

However will list the mandatory checklist briefly here as well:
* OPAL server should **always** be protected with a TLS/SSL certificate (i.e: HTTPS).
* OPAL server should **always** run in secure mode - meaning JWT token verification should be active.
* OPAL server should be configured with a **master token**.
* Sensitive configuration variables (i.e: environment variables with sensitive values) should **always** be stored in a dedicated **Secret Store**
  * Example secret stores: AWS Secrets Manager, HashiCorp Vault, etc.
  * **NEVER EVER EVER** store secrets as part of your source code (e.g: in your git repository).

## <a name="run-server"></a> How to run OPAL Server

This section explains how to run OPAL Server.

### Step 1: Get the server image from docker hub

If you run the docker image locally, you need docker installed on your machine.

Run this command to get the image:
```
docker pull authorizon/opal-server
```
If you run in a cloud environment (e.g: AWS ECS), specify `authorizon/opal-server` in your task definition or equivalent.

Running the opal server container is simply a command of [docker run](#example-docker-run), but we need to pipe to the OPAL server container the neccessary configration it needs via **environment variables**. The following sections will explain each class of configuration variables and how to set their values, after which we will demonstrate real examples.

### Step 2: Server config - broadcast interface

#### 1) Deploying the broadcast channel backbone service (optional)

When scaling the OPAL Server to **multiple workers** and/or **multiple containers**, we use a **broadcast channel** to sync between all the instances of OPAL Server. In order words, communication on the broadcast channel is **communication between OPAL servers**, and is not related to the OPAL client.

Under the hood, our interface to the broadcast channel **backbone service** is implemented by [encode/broadcaster](https://github.com/encode/broadcaster).

At the moment, the supported broadcast channel backbones are:
* Postgres LISTEN/NOTIFY
* Redis
* Kafka

Deploying the actual service used for broadcast (i.e: Redis) is outside the scope of this tutorial. The easiest way is to use a managed service (e.g: AWS RDS, AWS ElastiCache, etc), but you can also deploy your own dockers.

When running in production, you **should** run with multiple workers per server instance (i.e: container/node), if not multiple containers, and thus deploying the backbone service becomes **mandatory** for production environments.

#### 2) Declaring the broadcast uri environment variable

Declaring the broadcast uri is optional, depending on whether you deployed a broadcast backbone service and are also running with more than one OPAL server instance (multiple workers or multiple nodes). If you are running with multiple server instances (you **should** for production), declaring the broadcast uri is **mandatory**.

<table>
  <tbody>
    <tr>
      <th align="left">Env Var Name</th>
      <th align="left">Function</th>
    </tr>
    <tr>
      <td valign="top">OPAL_BROADCAST_URI</td>
      <td>
        <ul>
          <li>Broadcast channel backend.</li>
          <li>The format of the broadcaster URI string is specified <a href="https://github.com/encode/broadcaster#available-backends">here</a>.</li>
          <li>Example value: <code>OPAL_BROADCAST_URI=postgres://localhost/mydb</code></li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

#### 3) Declaring the number of uvicorn workers
As we mentioned in the previous section, each container can run multiple workers, and if you use more than one, you need a broadcast channel.

This is how you define the number of workers (pay attention: this env var is not prefixed with `OPAL_`):

Env Var Name | Function
:--- | :---
UVICORN_NUM_WORKERS | the number of workers in a single container (example value: `4`)

### Step 3: Server config - policy repo location

OPAL server is responsible to track policy changes and push them to OPAL clients.

At the moment, OPAL can tracks a git repository as the **policy source**.

#### (Mandatory) Repo location

<table>
  <tbody>
    <tr>
      <th align="left">Env Var Name</th>
      <th align="left">Function</th>
    </tr>
    <tr>
      <td valign="top">OPAL_POLICY_REPO_URL</td>
      <td>
        <ul>
          <li>The repo url the policy repo is located at.</li>
          <li>Must be available from the machine running OPAL (opt for public internet addresses).</li>
          <li>
            Supported URI schemes: <code>https://</code> and <code>ssh</code> (i.e: <code>git@</code>).
          </li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

#### (Optional) SSH key for private repos
If your tracked policy repo is <strong>private</strong>, you should declare this env var in order to authenticate and successfully clone the repo:

<table>
  <tbody>
    <tr>
      <th align="left">Env Var Name</th>
      <th align="left">Function</th>
    </tr>
    <tr>
      <td valign="top">OPAL_POLICY_REPO_SSH_KEY</td>
      <td>
        <ul>
          <li>Content of the var is a private crypto key (i.e: SSH key)</li>
          <li>
          You will need to register the matching public key with your repo. For example, see the <a href="https://docs.github.com/en/github/authenticating-to-github/adding-a-new-ssh-key-to-your-github-account">GitHub tutorial</a> on the subject.
          </li>
          <li>
            The passed value must be the contents of the SSH key in one line (replace new-line with underscore, i.e: <code>\n</code> with <code>_</code>)
          </li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

#### (Optional) Clone/pull settings
For these config vars, in most cases you are good with the default values:

<table>
  <tbody>
    <tr>
      <th align="left">Env Var Name</th>
      <th align="left">Function</th>
    </tr>
    <tr>
      <td valign="top">OPAL_POLICY_REPO_CLONE_PATH</td>
      <td>Where (i.e: target path) to clone the repo in your docker filesystem (not important unless you mount a docker volume)</td>
    </tr>
    <tr>
      <td valign="top">OPAL_POLICY_REPO_MAIN_BRANCH</td>
      <td>Name of the git branch to track for policy files (default: `master`)</td>
    </tr>
    <tr>
      <td valign="top">OPAL_POLICY_REPO_MAIN_REMOTE</td>
      <td>Name of the git remote to fetch new commits from  (default: `origin`)</td>
    </tr>
  </tbody>
</table>

### Step 4: Server config - policy repo syncing (change detection)

<!-- Move this to git repos document
* OPAL server feeds the policy code (`.rego` files) and static data files (`data.json` files) it detects in the policy repo to OPA as policy bundles (OPAL bundles are not the same as OPA bundles - but they are very similar).
* If new commits are pushed to the tracked git repository **that affect rego or data files**, the updated policy will be pushed to OPA automatically in realtime by OPAL. -->

Currently OPAL server supports two ways to detect changes in the policy git repo:
* **Polling in fixed intervals** - checks every X seconds if new commits are available.
* **Github Webhooks** - if the git repo is stored on github - you may setup a webhook (we plan to expand to generic webhook in the near future).

#### Option 1: Using polling (less recommended)
You may use polling by defining the following env var to a value different than `0`:

Env Var Name | Function
:--- | :---
OPAL_POLICY_REPO_POLLING_INTERVAL | the interval in seconds to use for polling the policy repo

#### Option 2: Using a webhook
It is much more recommended to use webhooks if your policy repo is stored in a supported service (currently Github, we are working on expanding this). Webhooks are much more efficient with network traffic, and won't conteminate your logs.

If your server is hosted at `https://opal.yourdomain.com` the webhook URL you must setup with your webhook provider (e.g: github) is `https://opal.yourdomain.com/webhook`. See [GitHub's guide on configuring webhooks](https://docs.github.com/en/developers/webhooks-and-events/creating-webhooks).

Typically you would need to share a secret with your webhook provider (authenticating incoming webhooks). You can use the OPAL CLI to create a cryptographically strong secret to use.

<a name="generate-secret"></a>Let's install the cli to a new python virtualenv:
```
pyenv virtualenv opal
pyenv activate opal
pip install opal-server
```

Now let's use the cli to generate a secret:
```
opal-server generate-secret
```

You must then configure the appropriate env var:

Env Var Name | Function
:--- | :---
OPAL_POLICY_REPO_WEBHOOK_SECRET | the webhook secret generated by the cli (or any other secret you pick)

For more info, check out this tutorial: [How to track a git repo](https://github.com/authorizon/opal/blob/master/docs/HOWTO/track_a_git_repo.md).

### Step 5: Server config - data sources
The OPAL server serves the **base data source configuration** for OPAL client. The configuration is structured as **directives** for the client, each directive specifies **what to fetch** (url), and **where to put it** in OPA data document hierarchy (destination path).

The data sources configured on the server will be fetched **by the client** every time it decides it needs to fetch the **entire** data configuration (e.g: when the client first loads, after a period of disconnection from the server, etc). This configuration must always point to a complete and up-to-date representation of the data (not a "delta").

You'll need to configure this env var:
Env Var Name | Function
:--- | :---
OPAL_DATA_CONFIG_SOURCES | Directives on **how to fetch** the data configuration we load into OPA cache when OPAL client starts, and **where to put it**.

#### <a name="encode-data-sources"></a>Data sources config schema
The **value** of the data sources config variable is a json encoding of the [ServerDataSourceConfig](https://github.com/authorizon/opal/blob/master/opal_common/schemas/data.py#L31) pydantic model.

#### Example value
```
{
    "config": {
        "entries": [
            {
                "url": "https://api.authorizon.com/v1/policy-config",
                "topics": [
                    "policy_data"
                ],
                "config": {
                    "headers": {
                        "Authorization": "Bearer FAKE-SECRET"
                    }
                }
            }
        ]
    }
}
```

Let's break down this example value (check the [schema](https://github.com/authorizon/opal/blob/master/opal_common/schemas/data.py#L31) for more options):

Each object in `entries` (schema: [DataSourceEntry](https://github.com/authorizon/opal/blob/master/opal_common/schemas/data.py#L8)) is a **directive** that tells OPAL client to fetch the data and place it in OPA cache using the [Data API](https://www.openpolicyagent.org/docs/latest/rest-api/#data-api).
* **From where to fetch:** we tell OPAL client to fetch data from the [**auth**orizon API](https://api.authorizon.com/redoc) (specifically, from the `policy-config` endpoint).
* **how to fetch (optional):** we can direct the client to use a specific configuration when fetching the data, for example here we tell the client to use a specific HTTP Authorization header with a bearer token in order to authenticate to the API.
* **Where to place the data in OPA cache:** although not specified, this entry uses the default of `/` which means at the root of OPA document hierarchy. You can specify another path with `dst_path` (check the [schema](https://github.com/authorizon/opal/blob/master/opal_common/schemas/data.py#L8)).

#### Encoding this value in an environment variable:
You can use the python method of `json.dumps()` to get a one line string:

```
❯ ipython

In [1]: x = {
   ...:     "config": {
   ...:         "entries": [
   ...:             ... # removed for brevity
   ...:         ]
   ...:     }
   ...: }

In [2]: import json
In [3]: json.dumps(x)
Out[3]: '{"config": {"entries": [{"url": "https://api.authorizon.com/v1/policy-config", "topics": ["policy_data"], "config": {"headers": {"Authorization": "Bearer FAKE-SECRET"}}}]}}'
```

Placing this value in an env var:
```
export OPAL_DATA_CONFIG_SOURCES='{"config": {"entries": [{"url": "https://api.authorizon.com/v1/policy-config", "topics": ["policy_data"], "config": {"headers": {"Authorization": "Bearer FAKE-SECRET"}}}]}}'
```

Please be advised, this will not work so great in docker-compose. Docker compose does not know how to deal with env vars that contain spaces, and it treats single quotes (i.e: `''`) as part of the value. But with `docker run` you should be fine.

#### Security
Since `OPAL_DATA_CONFIG_SOURCES` often contains secrets, in production you should place it in a [secrets store](#security-considerations).

### Step 6: Server config - security parameters

In this step we show how to configure the OPAL server **security parameters**.

Declaring these parameters and passing them to OPAL server will cause the server to run in **secure mode**, which means client identity verification will be active. All the values in this section are sensitive, in production you should place them in a [secrets store](#security-considerations).

#### When should i run in secure mode?
In a dev environment, secure mode is optional and you can skip this section.

However, in production environments you **should** run in secure mode.

#### 1) Generating encryption keys

Using a utility like [ssh-keygen](https://linux.die.net/man/1/ssh-keygen) we can easily generate the keys (on Windows try [SSH-keys Windows guide](https://phoenixnap.com/kb/generate-ssh-key-windows-10)).

```sh
ssh-keygen -t rsa -b 4096 -m pem
```

follow the instructions to save the keys to two files.

#### 2) Place encryption keys in environment variables

<table>
  <tbody>
    <tr>
      <th align="left">Env Var Name</th>
      <th align="left">Function</th>
    </tr>
    <tr>
      <td valign="top">OPAL_AUTH_PRIVATE_KEY</td>
      <td>
        <ul>
          <li>Content of the var is a private crypto key (i.e: SSH key)</li>
          <li>The private key is usually found in `id_rsa` or a similar file</li>
          <li>
            The passed value must be the contents of the SSH key in one line (replace new-line with underscore, i.e: <code>\n</code> with <code>_</code>)
          </li>
        </ul>
      </td>
    </tr>
    <tr>
      <td valign="top">OPAL_AUTH_PUBLIC_KEY</td>
      <td>
        <ul>
          <li>Content of the var is a public crypto key (i.e: SSH key)</li>
          <li>The public key is usually found in `id_rsa.pub` or a similar file</li>
          <li>
            The passed value must be the contents of the SSH key in one line.
            </li>
          <li>
            Usually public keys already fit into one line. If not, encoding is same as for the private key (replace new-line with underscore, i.e: <code>\n</code> with <code>_</code>).
          </li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

Example values:

If your private key looks like this (we redacted most of the key)
```
-----BEGIN OPENSSH PRIVATE KEY-----
XXX...
...
...XXX==
-----END OPENSSH PRIVATE KEY-----
```

Declare it like this (notice how we simply replace new lines with underscores):
```
export OPAL_AUTH_PRIVATE_KEY=-----BEGIN OPENSSH PRIVATE KEY-----_XXX..._..._...XXX==_-----END OPENSSH PRIVATE KEY-----
```

For public keys, it should be something like this:
```
export OPAL_AUTH_PUBLIC_KEY=ssh-rsa XXX ... XXX== some@one.com
```

#### 3) Configuring the master token

You can choose any secret you'd like, but as we've showed you [before](#generate-secret), the OPAL CLI can be used to generate cryptographically strong secrets easily.

```
opal-server generate-secret
```

You must then configure the master token like so

Env Var Name | Function
:--- | :---
OPAL_AUTH_MASTER_TOKEN | the master token generated by the cli (or any other secret you pick)

### Step 7: Putting it all together - running the server

To summarize, the previous steps guided you on how to pick the values of the configuration variables needed to run OPAL server.

We will now recap with a real example.

#### 1) Pull the server container image
```
docker pull authorizon/opal-server
```

#### 2) Define the environment variables you need

Multiple workers and broadcast channel (example values from step 2):
```
export OPAL_BROADCAST_URI=postgres://localhost/mydb
export UVICORN_NUM_WORKERS=4
```

Policy repo (example values from step 3):
```
export OPAL_POLICY_REPO_URL=https://github.com/authorizon/opal-example-policy-repo
```

Policy repo syncing with webhook (example values from step 4):
```
export OPAL_POLICY_REPO_WEBHOOK_SECRET=-cBlFnldg7WCGlj0jsivPWPA5vtfI2GWmp1wVx657Vk
```

Data sources configuration (example values from step 5):
```
export OPAL_DATA_CONFIG_SOURCES='{"config": {"entries": [{"url": "https://api.authorizon.com/v1/policy-config", "topics": ["policy_data"], "config": {"headers": {"Authorization": "Bearer FAKE-SECRET"}}}]}}'
```

Security parameters (example values from step 6):
```
export OPAL_AUTH_PRIVATE_KEY=-----BEGIN OPENSSH PRIVATE KEY-----_XXX..._..._...XXX==_-----END OPENSSH PRIVATE KEY-----
export OPAL_AUTH_PUBLIC_KEY=ssh-rsa XXX ... XXX== some@one.com
export OPAL_AUTH_MASTER_TOKEN=8MHfUU2rzRB59pdOHNNVVw3XLe3gl9YNw7vIXxJZNJo
```

#### 3) Run the container (local run example)
```
docker run -it \
  --env OPAL_BROADCAST_URI \
  --env UVICORN_NUM_WORKERS \
  --env OPAL_POLICY_REPO_URL \
  --env OPAL_POLICY_REPO_WEBHOOK_SECRET \
  --env OPAL_DATA_CONFIG_SOURCES \
  --env OPAL_AUTH_PRIVATE_KEY \
  --env OPAL_AUTH_PUBLIC_KEY \
  --env OPAL_AUTH_MASTER_TOKEN \
  -p 7002:7002 \
  authorizon/opal-server
```

#### 4) <a name="run-docker-prod"></a> Run the container in production
As we mentioned before, in production you will not use `docker run`.

Deployment looks somewhat like this:
* Declare your container configuration in code, e.g: AWS ECS task definition file, Helm chart, etc.
* All the secrets and sensitive vars should be fetched from a secrets store.
* Deploy your task / helm chart, etc to your cloud environment.
* Expose the server to the internet with HTTPS (i.e: use a valid SSL/TLS certificate).
* Keep your master token in a safe location (you will need it shortly to generate identity tokens).

## <a name="run-client"></a> How to run OPAL Client

Great! we have OPAL Server up and running. Let's continue and explains how to run OPAL Client.

### Step 1: Get the client image from docker hub

#### Running with inline OPA (default / recommended)
Run this command to get the image that comes with built-in OPA (recommended if you don't already have OPA installed in your environment):
```
docker pull authorizon/opal-client
```
If you run in a cloud environment (e.g: AWS ECS), specify `authorizon/opal-client` in your task definition or equivalent.

#### Running with standalone OPA
Otherwise, if you are already running OPA in your environment, run this command to get the standalone client image instead:
```
docker pull authorizon/opal-client-standalone
```

### Step 2: Obtain client JWT token (Optional)

In production environments, OPAL server **should** be running in **secure mode**, and the OPAL client must have a valid identity token (which is a signed JWT) in order to successfully connect to the server.

Obtaining a token is easy. You'll need the OPAL server's **master token** in order to request a JWT token.

Let's install the `opal-client` cli to a new python virtualenv (assuming you didn't [already create one](#generate-secret)):

```sh
# this command is not necessary if you already created this virtualenv
pyenv virtualenv opal
# this command is not necessary if the virtualenv is already active
pyenv activate opal
# this command installs the client cli
pip install opal-client
```

You can obtain a client token with this cli command:
```
opal-client obtain-token MY_MASTER_TOKEN --uri=https://opal.yourdomain.com --type client
```

If you don't want to use the cli, you can obtain the JWT directly from the deployed OPAL server via its REST API:
```
curl --request POST 'https://opal.yourdomain.com/token' \
--header 'Authorization: Bearer MY_MASTER_TOKEN' \
--header 'Content-Type: application/json' \
--data-raw '{
  "type": "client",
}'
```
The `/token` API endpoint can receive more parameters, as [documented here](https://opal.authorizon.com/redoc#operation/generate_new_access_token_token_post).

This example assumes that:
* You deployed OPAL server to `https://opal.yourdomain.com`
* The master token of your deployment is `MY_MASTER_TOKEN`.
  * However, if you followed our tutorial for the server, you probably generated one [here](#generate-secret) and that is the master token you should use.

example output:
```json
{
    "token": "eyJ0...8wsk",
    "type": "bearer",
    "details": { ... }
}
```

Put the generated token value (the one inside the `token` key) into this environment variable:

Env Var Name | Function
:--- | :---
OPAL_CLIENT_TOKEN | The client identity token (JWT) used for identification against OPAL server.

Example:
```sh
export OPAL_CLIENT_TOKEN=eyJ0...8wsk
```

### Step 3: Client config - server uri
Set the following environment variable according to the address of the deployed OPAL server:

Env Var Name | Function
:--- | :---
OPAL_SERVER_URL | The internet address (uri) of the deployed OPAL server. In production, you must use an `https://` address for security.

Example, if the OPAL server is available at `https://opal.yourdomain.com`:
```sh
export OPAL_SERVER_URL=https://opal.yourdomain.com
```
### Step 4: Client config - data topics (Optional)

You can configure which topics for data updates the client will subscribe to. This is great if you want more granularity in your data model, for example:
* **Enabling multi-tenancy:** you deploy each customer (tenant) with his own OPA agent, each agent's OPAL client will subscribe only to the relevant tenant's topic.
* **Sharding large datasets:** you split a big data set (i.e: policies based on user attributes and you have **many** users) to many instances of OPA agent, each agent's OPAL client will subscribe only to the relevant's shard topic.

If you do not specify data topics in your configuration, OPAL client will automatically subscribe to a single topic: `policy_data` (the default).

Use this env var to control which topics the client will subscribe to:

Env Var Name | Function
:--- | :---
OPAL_DATA_TOPICS | data topics delimited by comma (i,e: `,`)

Example value:
```sh
export OPAL_DATA_TOPICS=topic1,topic2,topic3
```

### Step 5: Client config - OPA runner parameters (Optional)
If you are running with inline OPA (meaning OPAL client runs OPA for you in the same docker image), you can change the default parameters used to run OPA.

In order to override default configuration, you'll need to set this env var:
Env Var Name | Function
:--- | :---
OPAL_INLINE_OPA_CONFIG | The value of this var should be an [OpaServerOptions](https://github.com/authorizon/opal/blob/master/opal_client/opa/options.py#L19) pydantic model encoded into json string. The process is similar to the one we showed on how to encode the value of [OPAL_DATA_CONFIG_SOURCES](#encode-data-sources).

### Step 6: Client config - Standalone OPA uri (Optional)

If OPA is deployed separately from OPAL (i.e: using the standalone image), you should define the URI of the OPA instance you want to manage with OPAL client with this env var:

Env Var Name | Function
:--- | :---
OPAL_POLICY_STORE_URL | The internet address (uri) of the deployed standalone OPA.

Example, if the standalone OPA is available at `https://opa.billing.yourdomain.com:8181`:
```sh
export OPAL_POLICY_STORE_URL=https://opa.billing.yourdomain.com:8181
```

### Step 7: Running the client

Let's recap the previous steps with example values:

#### 1) Get the client image
First, download opal client docker image:
```sh
docker pull authorizon/opal-client
```

#### 2) Set configuration
Then, declare configuration with environment variables:

```sh
# let's say this is the (shortened) token we obtained from opal server
export OPAL_CLIENT_TOKEN=eyJ0...8wsk
# and this is where we deployed opal server
export OPAL_SERVER_URL=https://opal.yourdomain.com
# and let's say we subscribe to a specific tenant's data updates (i.e: `tenant1`)
export OPAL_DATA_TOPICS=policy_data/tenant1
```

and let's assume we run opa inline with the default options.

#### 3) Run the container (local run example)
```
docker run -it \
  --env OPAL_CLIENT_TOKEN \
  --env OPAL_SERVER_URL \
  --env OPAL_DATA_TOPICS \
  -p 7000:7000 \
  -p 8181:8181 \
  authorizon/opal-client
```

Please notice opal client exposes two ports when running opa inline:
* OPAL Client (port `:7000`) - the OPAL client API (i.e: healthcheck, etc).
* OPA (port `:8181`) - the port of the OPA agent (OPA is running in server mode).

#### 4) Run the container in production
[Same instructions as for OPAL server](#run-docker-prod).

## <a name="push-updates"></a> How to push data updates from an authoritative source

Now that OPAL is live, we can use OPAL server to push updates to OPAL clients in real time.

[We have a separate tutorial on how to trigger updates](https://github.com/authorizon/opal/blob/master/docs/HOWTO/trigger_data_updates.md).

## <a name="troubleshooting"></a> Troubleshooting

#### Networking/DNS issues
In case the client cannot connect to the server, this may be a networking/dns issue in your setup.

OPAL client is configured to keep the connection with server open, and in case of disconnection - retry again and again to reconnect. But if something is wrong with the server address (server is down / unreachable / dns not configured) you might see the following logs:
```
2021-06-27T15:58:12.564384+0300 |fastapi_websocket_pubsub.pub_sub_client    | INFO  | Trying to connect to Pub/Sub server - ws://localhost:7002/ws
2021-06-27T15:58:12.564687+0300 |fastapi_websocket_rpc.websocket_rpc_client | INFO  | Trying server - ws://localhost:7002/ws
2021-06-27T15:58:12.567187+0300 |fastapi_websocket_rpc.websocket_rpc_client | INFO  | RPC connection was refused by server
...
```

#### OPAL Log verbosity
In case all you see in the logs is something like this:

```
2021-06-26T16:39:33.143143+0300 |opal_common.fetcher.fetcher_register    | INFO  | Fetcher Register loaded
2021-06-26T16:39:33.145399+0300 |opal_client.opa.runner                  | INFO  | Launching opa runner
2021-06-26T16:39:33.146177+0300 |opal_client.opa.runner                  | INFO  | Running OPA inline: opa run --server --addr=:8181 --authentication=off --authorization=off --log-level=info
2021-06-26T16:39:34.155196+0300 |opal_client.opa.runner                  | INFO  | Running OPA initial start callbacks
2021-06-26T16:39:34.156273+0300 |opal_client.data.updater                | INFO  | Launching data updater
2021-06-26T16:39:34.156519+0300 |opal_client.policy.updater              | INFO  | Launching policy updater
2021-06-26T16:39:34.156678+0300 |opal_client.data.updater                | INFO  | Subscribing to topics: ['policy_data']
2021-06-26T16:39:34.157030+0300 |opal_client.policy.updater              | INFO  | Subscribing to topics: ['policy:.']
```

It means that you logging verbosity does not include the RPC and Pub/Sub logs. You can control the logging verbosity with the following env vars:

Env Var Name | Function
:--- | :---
OPAL_LOG_MODULE_INCLUDE_LIST | A directive to include logs outputted by the modules appearing in the lists. e.g: setting `OPAL_LOG_MODULE_INCLUDE_LIST=["uvicorn.protocols.http"]` means that all log lines by the module `uvicorn.protocols.http` will be included in the log.
OPAL_LOG_MODULE_EXCLUDE_LIST | If you want less logs, you can ignore logs emitted by these modules. Opposite of `OPAL_LOG_MODULE_INCLUDE_LIST`. To get all logs and make sure nothing is filtered, set the env var like so: `OPAL_LOG_MODULE_EXCLUDE_LIST=[]`.
OPAL_LOG_LEVEL | Default is `INFO`, you can set to `DEBUG` to get more logs, or to higher other log level (less recommended).

#### Inline OPA logs
If running OPA inline, OPAL can output the Inline OPA logs in several formats.

Env Var Name | Function
:--- | :---
OPAL_INLINE_OPA_LOG_FORMAT | log format of the logs returned by the OPA agent that is being monitored and run by OPAL client. Can be `none`, `minimal`, `http`, or `full`. The recommended value to set is `http` (nicer formatting).