# Get started with OPAL python packages

This guide will teach you how to setup and use OPAL as Python packages (python 3.7 >) with its CLI

## Table of Contents
1. Setup OPAL-server
2. Setup OPAL-client
3. Setup server and client in secure Mode
- General Points


## Intro
Getting Started with OPAL is easy - we'll install our OPAL-server to manage all the OPAL-client's we deploy.
We'll deploy OPAL-clients (along side policy agents).

This HOW-TO focuses on setting-up OPAL with its packages and CLI interface, this guide is better to understand the main configurations of OPAL. There's also a separate guide for [setting-up OPAL from pre-built docker images](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_using_docker.md).

### NOTES:
- Make sure your system is running Python 3.7 or higher

- Ideally install OPAL into a clean [virtual-env](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/)

- Both opal-server and opal-client can be configured using environment-variables, [.env / .ini](https://pypi.org/project/python-decouple/#env-file) files , and command-line options (later overrides previous).

- Passing lists (e.g. client's `--data-topics`):
    - pass delimited by "," with env-vars i.e. `OPAL_DATA_TOPICS=topic1,topic2,topic3 opal-client run`
    - and as multi-options for cmd options i.e. `opal-client  --data-topics topics1 --data-topics topics2 --data-topics topics3 run`

- Top-level CLI options listed in `--help` are available under the same name as env-vars (simply convert to uppercase and replace "-" with "_", prefix with 'OPAL' )
for example `OPAL_SERVER_PORT=1337 opal-server run` is equivalent to `opal-server --server-port 1337 run`


----------------------------

## Setup OPAL-server

1. ### Install OPAL-server using pip
    ```sh
    pip install opal-server
    ```
    - Once installed your shell will have access to the `opal-server` command.

        <p><a href="https://asciinema.org/a/XyDg1ot2Q6UOsWOkiSxGVSJmx?t=1" target="_blank"><img src="https://asciinema.org/a/XyDg1ot2Q6UOsWOkiSxGVSJmx.svg"/></a>
        </p>
    - if the command isn't available try deactivating/activating the virtual-env
    - run `opal-server --help` to see all the options and commands
    - run the `opal-server print-config` to see all the possible configuration keys and their values (as read from defaults, evn-vars, .env, .ini, and the command-line)


2. ### Run opal-server

    ### Simple run with GIT repo watching
    - We can run the server with the run command - i.e. `opal-server run`
    -  Once the server is running you can check out its Open-API live docs at [/docs](http://localhost:7002/docs) or [/redoc](http://localhost:7002/redoc) (These links assume you have the server running on locally the default port - **localhost:7002** )

    - ### Polling Policy from GIT:
        - The most basic way to run the server is just with a GIT repository to watch for policy-changes and get the policy from.
        - Simplest of those is using a public repository, and simply polling on it (with `OPAL_POLICY_REPO_URL` and `OPAL_POLICY_REPO_POLLING_INTERVAL`)
            ```sh
            #Have the opal server monitor a repo every 60 seconds
            OPAL_POLICY_REPO_URL=https://github.com/authorizon/opal-example-policy-repo.git  opal-server --policy-repo-polling-interval 60 run
            ```
            <p><a href="https://asciinema.org/a/4gkfGDR45IeR0Zx3y2zB1Vg9T?t=1" target="_blank"><img src="https://asciinema.org/a/4gkfGDR45IeR0Zx3y2zB1Vg9T.svg"/></a></p>

    - ### Policy GIT Webhook:
        - Better GIT watching can be achieved via configuring a webhook back to the OPAL_SERVER's webhook route. Say your server is hosted on `opal.yourdomain.com` the webhook URL will be `opal.yourdomain.com/webhook`
        - see [GitHub's guide on configuring webhooks](https://docs.github.com/en/developers/webhooks-and-events/creating-webhooks)
        - use `OPAL_POLICY_REPO_WEBHOOK_SECRET` to configure a secret you can share with the webhook provider (authenticating incoming webhooks)
            - you can use `opal-server generate-secret` to create a cryptographically strong secret to use

    - ### Additional GIT repository settings
        - Use `POLICY_REPO_SSH_KEY` to authenticate to a **private repository** (see Git hosts for hot to configure the key - for example- [Github SSH Key](https://docs.github.com/en/github/authenticating-to-github/adding-a-new-ssh-key-to-your-github-account))
            - The passed value for key can either be a file path, or the contents of the SSH-key (with newlines replaced with '_')
        - Use `OPAL_POLICY_REPO_CLONE_PATH`, `OPAL_POLICY_REPO_MAIN_BRANCH`, `OPAL_POLICY_REPO_MAIN_REMOTE`, etc. to control how the repo is cloned



    ### Simple run with Data source configuration
    In addition to policy updates (as seen in above section) the OPAL-server can also facilitate data updates, directing OPAL-clients to fetch the needed data from various sources.
    see [how to trigger data updates guide](https://github.com/authorizon/opal/blob/master/docs/HOWTO/trigger_data_updates.md)
    CLI example:
    <p><a href="https://asciinema.org/a/JYBzx1VrqJ17QnvmOnDYylOE6?t=1" target="_blank"><img src="https://asciinema.org/a/JYBzx1VrqJ17QnvmOnDYylOE6.svg"/></a></p>

    ### Production run
    For production we should set the server to work with a production server ([GUNICORN](https://gunicorn.org/)) and backbone pub/sub.

    - Gunicorn
        - simply use the `run` command with the `--engine-type gunicorn` option.
        ```sh
        opal-server run --engine-type gunicorn
        ```

        - (run `opal-server run --help` to see more info on the `run` command)
        - use `--server-worker-count` to control the amount of workers (default is set to cpu-count)
        - You can of course put another server or proxy (e.g. NGNIX, ENVOY) in front of the OPAL-SERVER, instead of or in addition to Gunicorn

    - Backbone Pub/Sub
        - While OPAL-servers provide a lightweight websocket pub/sub channel for the clients; in order for all OPAL-servers (workers of same server, and of course servers on other nodes) to be synced (And in turn their clients to be synced) they need to connect through a shared channel - which we refer to as the backbone pub/sub or broadcast channel.
        - Backbone Pub/Sub options:  Kafka, Postgres LISTEN/NOTIFY, Redis
        - Use the `broadcast-uri` option (or `OPAL_BROADCAST_URI` env-var) to configure an OPAL-server to work with a backbone.
        - for example `OPAL_BROADCAST_URI=postgres://localhost/mydb opal-server run`

    - Put it all together:
        ```sh
        OPAL_BROADCAST_URI=postgres://localhost/mydb opal-server run --engine-type gunicorn
        ```

    ### Server Secure Mode
    OPAL-server can run in secure mode, signing and verifying [Json Web Tokens](https://en.wikipedia.org/wiki/JSON_Web_Token) for the connecting OPAL-clients.
    To achieve this we need to provide the server with a private and public key pair.
    In addition we need to provide the server with a master-token (random secret) that the CLI (or other tools) could use to connect to ask it and generate the aforementioned signed-JWTs.

    - Generating encryption keys
      - Using a utility like [ssh-keygen](https://linux.die.net/man/1/ssh-keygen) we can easily generate the keys (on Windows try [SSH-keys Windows guide](https://phoenixnap.com/kb/generate-ssh-key-windows-10))
        ```sh
        ssh-keygen -t rsa -b 4096 -m pem
        ```
        follow the instructions to save the keys to two files.
      - If you created the keys with a passphrase, you can supply the passphrase to the server via the `OPAL_AUTH_PRIVATE_KEY_PASSPHRASE` option
      - You can provide the keys to OPAL-server via the `OPAL_AUTH_PRIVATE_KEY` and `OPAL_AUTH_PUBLIC_KEY` options
      - in these vars You can either provide the path to the keys, or the actual strings of the key's content (with newlines replaced with "_")

    - Master-secret
        - You can choose any secret you'd like, but to make life easier OPAL's CLI include the generate-secret command, which you can use to generate cryptographically strong secrets easily.
            ```sh
            opal-server generate-secret
            ```
        - provide the master-token via `OPAL_AUTH_MASTER_TOKEN`

    - run the server with both keys and and master-secret

        ```sh
        # Run server
        # in secure mode -verifying client JWTs (Replace secrets with actual secrets ;-) )
        # (Just to be clear `~` is the user's homedir)
        export OPAL_AUTH_PRIVATE_KEY=~/opal
        export OPAL_AUTH_PUBLIC_KEY=~/opal.pub
        export OPAL_AUTH_MASTER_TOKEN="RANDOM-SECRET-STRING"
        opal-server run
        ```

    - Once the server is running we can obtain a JWT identifying our client
      - We can either obtain a JWT with the CLI
        ```sh
        opal-client obtain-token $OPAL_AUTH_MASTER_TOKEN --server-url=$YOUR_SERVERS_ADDRESS
        ```
      - <a name="obtain-token-api"></a>Or we can obtain the JWT directly from the deployed OPAL server via its REST API:
        ```
        curl --request POST 'https://opal.yourdomain.com/token' \
        --header 'Authorization: Bearer MY_MASTER_TOKEN' \
        --header 'Content-Type: application/json' \
        --data-raw '{
          "type": "client",
        }'
        ```
        This code example assumes your opal server is at https://opal.yourdomain.com and that your master token is `MY_MASTER_TOKEN`. The `/token` API endpoint can receive more parameters, as [documented here](https://opal.authorizon.com/redoc#operation/generate_new_access_token_token_post).



-----


## Setup OPAL-Client

### Install
- Install OPAL-client
    ```sh
    pip install opal-client
    ```
- Install a policy-agent next to the OPAL-client
    - follow [these instructions to install OPA](https://www.openpolicyagent.org/docs/latest/#1-download-opa)
    - If you want OPAL to execute OPA for you (and act as  a watchdog for it) make sure it can find the `opa` program, by [adding it to the $PATH](https://unix.stackexchange.com/questions/3809/how-can-i-make-a-program-executable-from-everywhere).
    - Note: the client needs network access to this agent to be able to administer updates to it.


### Simple run
- Use the client's `run` command
- try:
    ```sh
    # general help commands and options
    opal-client --help
    # help for the run command
    opal-client run --help
    ```
- Just like the server all top-level options can be configured using environment-variables, [.env / .ini](https://pypi.org/project/python-decouple/#env-file) files , and command-line options (later overrides previous).
- Key options:
    - Use options starting with `--server` to control how  the client connects to the server (mainly `--server-url` to point at the server)
    - Use options starting with `--client-api-` options to control how the client's API service is running
    - Use `--data-topics` to control which topics for data updates the client would subscribe to.
    - Use `--policy-subscription-dirs`

### Production run
Unlike the server, the opal-client currently supports working only with a single worker process (so there's no need to run it with Gunicorn).
This will change in future releases.

### Client Secure Mode
- [Run the server in secure mode](#server-secure-mode)
- Using the master-token you assigned to the server obtain a client JWT
    ```sh
    opal-client obtain-token $OPAL_AUTH_MASTER_TOKEN --server-url=$YOUR_SERVERS_ADDRESS
    ```
    You can also use the REST API to obtain the token, [as shown here](#obtain-token-api).
- run the client with env-var `OPAL_CLIENT_TOKEN` or cmd-option `--client-token` to pass the JWT obtained from the server
    ```sh
    export OPAL_CLIENT_TOKEN="JWT-TOKEN-VALUE`
    opal-client run
    ```

### Client install & run recording:

<p><a href="https://asciinema.org/a/oy4nA9E7RbOyiUx6evACUuLNd?t=1" target="_blank"><img src="https://asciinema.org/a/oy4nA9E7RbOyiUx6evACUuLNd.svg"/></a>
</p>

