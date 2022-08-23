# OPAL Scopes

OPAL Scopes allows OPAL to serve different policies and data sources, serving them to multiple clients. Every scope contains its own policy and data sources. All clients using the same Scope ID will get the same policy and data.

Scopes are an easy way to use OPAL with multiple Git repositories (or other sources of policy), and are a core feature to enable using OPAL itself as a multi-tenant service.

Scopes are dynamic, and can be be created on the fly through the scopes API (`/scopes`)

## Setting up scopes
> #### Prerequisites
> Scopes are supported in OPAL 0.2.0 and above. Use the [provided docker-compose example](https://github.com/permitio/opal/blob/master/docker/docker-compose-scopes-example.yml) to quickly get started.

1. Use a REST API call to create or change a scope:

```http request
PUT /scopes
Content-Type: application/json

{
  "scope_id": "internal",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/company/policy",
    "auth": {
      "auth_type": "github_token",
      "token": "github_token"
    },
    "directories": [
      "internal"
    ],
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": true,
    "branch": "main"
  },
  "data": {
    "entries": []
  }
}
```

```http request
PUT /scopes
Content-Type: application/json

{
  "scope_id": "external",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/company/policy",
    "auth": {
      "auth_type": "github_token",
      "token": "github_token"
    },
    "directories": [
      "external"
    ],
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": true,
    "branch": "main"
  },
  "data": {
    "entries": []
  }
}
```

2. Launch OPAL Client with a scope:
```shell
OPAL_CLIENT_TOKEN=... OPAL_SCOPE_ID=internal opalc
```
