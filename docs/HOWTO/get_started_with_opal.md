# How to Get Started with OPAL  

This guide will teach you how to setup and use OPAL as Python packages (python 3.7 >) with its CLI 

## Table of Contents
1. Setup OPAL-server
2. Setup OPAL-client
3. Setup server and client in secure Mode 
- General Points


## Intro
Getting Started with OPAL is easy - we'll install our OPAL-server to manage all the OPAL-client's we deploy.
We'll deploy OPAL-clients (along side policy agents).

This HOW-TO focuses on setting-up OPAL with its packages and CLI interface, this guide is better to understand the main configurations of OPAL. There's also a separate guide for [setting-up OPAL from pre-built docker images](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_with_docker.md).

### NOTES: 
- Make sure your system is running Python 3.7 or higher 

- Ideally install OPAL into a clean [virtual-env](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) 

- Both opal-server and opal-client can be configured using environment-variables, [.env / .ini](https://pypi.org/project/python-decouple/#env-file) files , and command-line options (later overrides previous).

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
     - 
        

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







-----


## Setup OPAL-Client (work in progress)

- Install OPAL-client
    ```sh
    pip install opal-client
    ```    
- Install a policy-agent next to the OPAL-client
    - follow [these instructions to install OPA](https://www.openpolicyagent.org/docs/latest/#1-download-opa)
    - the client needs network access to this agent to be able to administer updates to it.



