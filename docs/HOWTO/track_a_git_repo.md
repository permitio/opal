# Policy syncing with git

This document describes the policy syncing feature of OPAL (policy-code and static data).

## How policy syncing works

### 1) OPAL Server tracks a git branch
OPAL server is configured to track a **git repo**, and in that repo - a specific **branch**. By **tracking** the branch, we mean that OPAL server will always keep the most up-to-date "picture" of this branch.

More technically, OPAL Server will:
* Clone the repo, checked out to the tracked branch.
* Detect changes in the tracked branch upstream.
* Upon detecting new commits in the branch upstream, **pull** these changes into its local checkout.

Currently OPAL server supports two ways to detect changes in the tracked repo:
  * **Polling in fixed intervals** - checks every `X` seconds if there are new commits in the upstream branch by running `git fetch` internally.
  * **Github Webhooks** - A webhook means that the service storing the repo (e.g: GitHub) will issue an HTTP REST request to OPAL server upon each `push` event.

At the moment, only GitHub-hosted repos support webhooks. We plan to expand to more services (e.g: bitbucket) and/or a generic webhook interface in the near future.

### 2) OPAL Client subscribes to policy update notifications
OPAL client can subscribe to multiple policy topics, each policy topic is formatted as `policy:{path}` where path is a **directory** in the policy git repository (**relative path** to the root of the repository).

The policy directories the client will subscribe to are specified by the environment variable `OPAL_POLICY_SUBSCRIPTION_DIRS` passed to the client. The default is `"."` meaning the root directory in the branch (i.e: essentially all `.rego` and `data.json` files in the branch).

Let's look at at a more complex example. Let's say we have a multi-tenant application in the cloud with an on-prem component in each customer site. We want to apply the same base policy to all tenants, but also to allow special rules (different policy) per tenant.

Assume our policy repository looks like this:
```
.
├── default
│   ├── data.json
│   └── rbac.rego
└── tenants
    ├── tenant1
    │   ├── data.json
    │   └── location.rego
    ├── tenant2
    │   ├── billing.rego
    │   └── data.json
    └── tenant3
    │   ├── ...
    ...
```
We can see the tenant 1 has a special policy for user location (e.g: special rules for users interacting with the application from outside the US), while tenant 2 has special rules around billing (i.e: allow some access only to paying users, etc).

We'll deploy a different OPAL client as part of our on-prem/edge container in each customer vpc, for simplicity let's call them `edge1`, `edge2` and `edge3`:

* `edge1` will set `OPAL_POLICY_SUBSCRIPTION_DIRS=default:tenants/tenant1` meaning its policy bundles will include both policy files found under the `default` directory as well policy files under `tenants/tenant1`, but not policy files under `tenant2`, etc.
* Similarly:
  * `edge2` will set `OPAL_POLICY_SUBSCRIPTION_DIRS=default:tenants/tenant2`.
  * `edge3` will set `OPAL_POLICY_SUBSCRIPTION_DIRS=default:tenants/tenant3`.

### 3) <a name="policy-update-message"></a>OPAL Server notifies his OPAL clients about policy updates
Upon learning about **new commits** in the tracked branch, and assuming these new commits include changes **that affect rego or data files**, OPAL server will push an update message via pub/sub to its OPAL clients.

* The update message will include the most recent (i.e: top-most) commit hash in the tracked branch.
* Each OPAL client will only be notified about changes in the directories he is subscribed to.

i.e: example **policy update message** assuming a commit changed the `billing.rego` file:
```
{
  "topic": "policy:tenant2",
  "data": "5cdf36a7510f6ecc9e89cceb0ae0672c67ddb34c"
}
```

Notice that the update message **does not** include any actual policy files, the OPAL client is responsible to fetch a new policy bundle upon being notified about relevant updates.

### 4) OPAL Client fetches policy bundles from OPAL Server
OPAL clients fetch policy bundles by calling the `/policy` endpoint on the OPAL server.

The client may present a **base hash** - meaning the client already has the policy files up until the **base hash** commit. If the server is presented with the base hash, the server will return a **delta bundle**, meaning only changes (new, modified, renamed and deleted files) will be included in the bundle.

The client will fetch a new policy bundle upon the following events:
* When first starting up, the client will fetch a **complete** policy bundle.
* After the initial bundle, the client will ask **delta** policy bundles (only changes):
  * After a disconnect from the OPAL server (e.g: if the server crashed, etc)
  * After receiving a [policy update message](#policy-update-message)


#### Policy bundle manifest - serving dependant policy modules
The policy bundle contains a `manifest` list that contains the paths of all the modules (.rego or data.json) that are included in the bundle. The `manifest` list is important! It controls the **order** in which the OPAL client will load the policy modules into OPA.

OPA rego modules can have dependencies if they use the [import statement](https://www.openpolicyagent.org/docs/latest/policy-language/#imports).

You can control the manifest contents and ensure the correct loading of dependent OPA modules. All you have to do is to put a `.manifest` file in the root directory of your policy git repository (like shown in [this example repo](https://github.com/authorizon/opal-example-policy-repo)).

**The `.manifest` file is optional!!!** If there is no manifest file, OPAL will load the policy modules it finds in alphabetical order.

The format of the `.manifest` file you should adhere to:
* File encoding should be standard (i.e: UTF-8)
* Lines should be separated with newlines (`\n` character)
* Each line should contain the relative path to one file in the repo (i.e: a `.rego` file or `data.json` file).
* File paths should appear in the order you want to load them into OPA.
* If you want to use a different file name other than `.manifest`, you can set another value to the env var `OPAL_POLICY_REPO_MANIFEST_PATH`.

For example, if you look in the [example repo](https://github.com/authorizon/opal-example-policy-repo), you would see that the `rbac.rego` module imports the `utils.rego` module (the line `import data.utils` imports the `utils` package). Therefore in the manifest, `utils.rego` appears first because it needs to be loaded into OPA before the `rbac.rego` policy is loaded (otherwise OPA will throw an exception due to the import statement failing).

#### Policy bundle API Endpoint
The [policy bundle endpoint](https://opal.authorizon.com/redoc#operation/get_policy_policy_get) exposes the following params:
* **path** - path to a directory inside the repo, the server will include only policy files under this directory. You can pass the **path** parameter multiple times (i.e: to include files under several directories).
* **base_hash** - include only policy files that were changed (added, updated, deleted or renamed) after the commit with the **base hash**. If this parameter is included, the server will return a **delta bundle**, otherwise the server will return a **complete bundle**.

Let's look at some real API call examples. The opal server in these example track [our example repo](https://github.com/authorizon/opal-example-policy-repo).

Example fetching a complete bundle:
```sh
curl --request GET 'https://opal.authorizon.com/policy?path=.'
```

Response (a complete bundle is returned):
```json
{
    "manifest": [
        "data.json",
        "rbac.rego"
    ],
    "hash": "ac16d91b84f578954ccd1c322b1f8f99d44248c0",
    "old_hash": null,
    "data_modules": [
        {
            "path": ".",
            "data": "<CONTENTS OF data.json>"
        }
    ],
    "policy_modules": [
        {
            "path": "rbac.rego",
            "package_name": "app.rbac",
            "rego": "<CONTENTS OF rbac.rego>"
        }
    ],
    "deleted_files": null
}
```

Example fetching a delta bundle:
```sh
curl --request GET 'https://opal.authorizon.com/policy?base_hash=503e6f9821eb036ce6a4207a45ddbe147f1a0a7b&path=.'
```

This time the response is a delta bundle, the `envoy.rego` file was deleted and `rbac.rego` and `data.json` were added:
```json
{
    "manifest": [
        "data.json",
        "rbac.rego"
    ],
    "hash": "ac16d91b84f578954ccd1c322b1f8f99d44248c0",
    "old_hash": "503e6f9821eb036ce6a4207a45ddbe147f1a0a7b",
    "data_modules": [
        {
            "path": ".",
            "data": "<CONTENTS OF data.json>"
        }
    ],
    "policy_modules": [
        {
            "path": "rbac.rego",
            "package_name": "app.rbac",
            "rego": "<CONTENTS OF rbac.rego>"
        }
    ],
    "deleted_files": {
        "data_modules": [],
        "policy_modules": [
            "envoy.rego"
        ]
    }
}
```

## Setting up the OPAL Server - options for policy change detection

### Option 1: Using polling (less recommended)
You may use polling by defining the following environment variable to a value different than `0`:

Env Var Name | Function
:--- | :---
OPAL_POLICY_REPO_POLLING_INTERVAL | the interval in seconds to use for polling the policy repo

### Option 2: Using a webhook
If your server is hosted at `https://opal.yourdomain.com`, the URL you must setup with your webhook provider (e.g: github) is `https://opal.yourdomain.com/webhook`. See [GitHub's guide on configuring webhooks](https://docs.github.com/en/developers/webhooks-and-events/creating-webhooks).

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

#### Example setting up a webhook
Generate a secret:
```
❯ opal-client generate-secret
OQ3M81ECbeJEIka4MhgPalSbxVLLe91GBZyiVtPEUsM
```

Pass the secret as config when [running OPAL Server](https://github.com/authorizon/opal/blob/master/docs/HOWTO/get_started_with_opal_using_docker.md#step-7-putting-it-all-together---running-the-server):
```sh
export OPAL_POLICY_REPO_WEBHOOK_SECRET=OQ3M81ECbeJEIka4MhgPalSbxVLLe91GBZyiVtPEUsM
docker run -it \
  # more params ...
  --env OPAL_POLICY_REPO_WEBHOOK_SECRET \
  # more params ...
  -p 7002:7002 \
  authorizon/opal-server
```
On your GitHub project page, go to Settings -> Webhooks:

<img src="https://i.ibb.co/B28b9j1/webhooks1.png" alt="webhooks1" border="0">

And then fill the following values:
* The webhook URL exposed by your OPAL server, example: `https://opal.yourdomain.com/webhook`
* The webhook secret you generated
* Select only the `push` event
* And click on **Add webhook**.

<img src="https://i.ibb.co/3CkRrq5/webhooks2.png" alt="webhooks2" border="0">