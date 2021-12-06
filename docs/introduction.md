

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
    export OPAL_POLICY_REPO_URL=https://github.com/authorizon/opal-example-policy-repo.git
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







[Code modules](docs/modules.md) review



### "HOW-TO"s:
  
  [How to get started with OPAL (Packages and CLI)](docs/HOWTO/get_started_with_opal.md)

  [How to get started with OPAL (Container Images)](docs/HOWTO/get_started_with_opal_using_docker.md)
  [How to trigger Data Updates via OPAL](docs/HOWTO/trigger_data_updates.md)

  [How to extend OPAL to fetch data from your sources with FetchProviders](docs/HOWTO/write_your_own_fetch_provider.md)

  [How to configure OPAL (basic concepts)](docs/HOWTO/configure_opal.md)



# <a name="community"></a>

 
    
    