# Triggering Data Updates
OPAL allows for other components to notify it (and through it all the OPAL clients , and their next-door policy agents) of data updates, triggering each client [subscribed to the published topic] to fetch the data it needs.

## What is this good for?
Lets try an example - say your application has a billing service, and you want to allow access only to users who have billing enabled (enforced via a policy agent). 
You now need changes to the state of the billing service to be propagated to each of the enforcement points/agents (and preferably instantly [Users who've paid - don't like to wait 😅 ]). </br>
With the OPAL's data-update-triggers feature the billing-service, another service monitoring it, or even a person can trigger updates as they need - knowing OPAL will take it from there to all the points that need it.

# How to trigger updates
There are a few ways to trigger updates:</br>

## The publish-data-update CLI command
 - Can be run both from opal-client and opal-server.


## Write your own - OpenAPI
- All the APIs in opal are OpenAPI / Swagger based (via FastAPI).
- Check out the [API docs on your running OPAL-server](http://localhost:7002/docs#/Data%20Updates/publish_data_update_event_data_config_post) -- this link assumes you have the server running on `http://localhost:7002`
- You can also [generate an API-client](https://github.com/OpenAPITools/openapi-generator) in the language of your choice using the [OpenAPI spec provided by the server](http://localhost:7002/openapi.json) 

## Write your own - import code from the OPAL's packages
- One of the greta things about OPAL being written in Python is that you can easily reuse its code.
See the code for the `DataUpdate` model at [opal_common/schemas/data.py](https://github.com/authorizon/opal/blob/master/opal_common/schemas/data.py) and use it within your own code to send an update to the server





