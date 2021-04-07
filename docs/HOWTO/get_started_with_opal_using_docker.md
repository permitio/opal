
# Get started with OPAL via docker containers
## Note: 🚧  Work in progress 🚧

## Install & run
- Server
    ```sh
    docker pull authorizon/opal-server
    ```
    ```
    docker run authorizon/opal-server
    ```

- Client (prebuilt with OPA inside)
    ```shell
    docker pull authorizon/opal-client
    ```
    ```
    docker run authorizon/opal-client
    ```


# Configuration 
All the top level options (those that aren't given to specific CLI commands) are available as environment variables as well (simply convert to uppercase and replace "-" with "_", prefix with 'OPAL').
 - You can run the opal-server / opal-client CLIs with --help to see all the available values.   
 - or you can check out the config sources directly - [opal_client/config.py](https://github.com/authorizon/opal/blob/master/opal_client/config.py) , [opal_server/config.py](https://github.com/authorizon/opal/blob/master/opal_server/config.py), and [opal_common/config.py](https://github.com/authorizon/opal/blob/master/opal_common/config.py)
 - Check-out the [CLI guide for configuration examples](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal.md)
