# Fetch Providers
FetchProviders are the components OPAL uses to fetch data from sources on demand.

Fetch providers are designed to be extendable, and you can easily create more fetch providers to enable OPAL to fetch data from your own unique sources (e.g. a SaaS service, a new DB, your own proprietary solution, ...)


## Writing your own fetch providers
1. ### The basics
    All FetchProviders are classes that derive from ```BaseFetchProvider```.
    FetchProviders are loaded into the fetch-register from the Python modules the configuration points to ([OPAL_FETCH_PROVIDER_MODULES](https://github.com/authorizon/opal/blob/66b139d10caf27b590a350b750d988c88a27acca/opal_common/config.py#L38))
    - Providers use the FetcherEvent initialized in ```self._event``` and specifically the ```FetcherConfig``` configuration in ```self._event.config```
    - Providers implement a ```_fetch_``` method to access and fetch data from the data-source (indicated by ```self._event.url```)
    - the FetchingEngine workers invokes a provider's ```.fetch()``` and ```.process()``` which proxy to ```_fetch_``` and ```_process_``` accordingly
2. ### Deriving from BaseFetchProvider and implementing Fetch & Process
    - See a core example for an [HTTPFetcher - here](https://github.com/authorizon/opal/blob/master/opal_common/fetcher/providers/http_get_fetch_provider.py)
    1. Create a new class deriving from ```BaseFetchProvider``` 
    2. Override ```_fetch_`` to implement the fetching itself
    3. Optionally override ```_process_``` to mutate the data before returning it (for example converting a JSON string to an actual object)
    4. Manage a context
        - If you require a context for (cleanup or guard)
        Simply override ``` __aenter__``` and ```__aexit__```
        - fetcher workers call providers with ```async with``` around fetch and process.
3. ### FetcherConfig
    - Each FetcherProvider might require specific values that will be passed to it as part of its configuration. For such a case implement a Pydantic model (Deriving from FetcherConfig) to go alongside your new provider.
    - e.g. for HTTP request fetcher 
        ```python
        class HttpGetFetcherConfig(FetcherConfig):
            headers: dict = None
            is_json: bool = True
            process_data: bool = True
        ```
    - These should be used when triggering your provider from a ```DataUpdate``` via the OPAL-server's [DataUpdatePublisher](https://github.com/authorizon/opal/blob/master/opal/server/data/data_update_publisher.py)

4. ### Saving and registering your provider
    The [fetcher-register](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/fetcher_register.py) loads the providers and makes them available for fetcher-workers.
    The fetcher register loads the python packages indicated by the given configuration ([OPAL_FETCH_PROVIDER_MODULES](https://github.com/authorizon/opal/blob/master/b1aaa3f9e30e903ca0053cba0a6525bfb4151e78/opal/common/config.py#L36)) and searches for classes deriving from ```BaseFetchProvider``` in them.

    - You can add your providers by supplying module files-
        - By adding python files to the default fetcher folder - 'opal/common/fetcher/providers'
        - By creating a package - i.e. a new folder with ```__init__.py``` 
            - read about [configuring python packages here](https://docs.python.org/3/tutorial/modules.html#packages)
            - you can set your ```__all__``` variable in your ```__init__.py``` to point to the modules you'd like
            - or expose them all using emport.dynamic_all (as shown [here](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/providers/__init__.py))

    - Loading from PyPi
        - _coming soon_

## Module / Class structure
- [FetchingEngine](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/engine/fetching_engine.py) 
    - [fetch_worker](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/engine/fetch_worker.py)
- [BaseFetchProvider](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/fetch_provider.py)
- [FetcherRegister](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/fetcher_register.py)
- [FetcherConfig](https://github.com/authorizon/opal/blob/master/opal/common/fetcher/events.py)

