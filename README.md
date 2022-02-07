<p  align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=170 alt="opal" border="0" />
</p>
<h1 align="center">
⚡OPAL⚡
</h1>

<h2 align="center">
Open Policy Administration Layer
</h2>

<a href="https://github.com/permitio/opal/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/permitio/opal/workflows/Tests/badge.svg" alt="Tests">
</a>
<a href="https://pypi.org/project/opal-server/" target="_blank">
    <img src="https://img.shields.io/pypi/v/opal-server?color=%2331C654&label=OPAL%20Server%20%28PyPi%29" alt="Package">
</a>
<a href="https://pypi.org/project/opal-client/" target="_blank">
    <img src="https://img.shields.io/pypi/v/opal-client?color=%2331C654&label=OPAL%20Client%20%28PyPi%29" alt="Package">
</a>
<a href="https://pepy.tech/project/opal-server" target="_blank">
    <img src="https://static.pepy.tech/personalized-badge/opal-server?period=total&units=international_system&left_color=black&right_color=blue&left_text=Downloads" alt="Downloads">
</a>

<a href="https://hub.docker.com/r/permitio/opal-server" target="_blank">
    <img src="https://img.shields.io/docker/pulls/permitio/opal-server?label=Docker%20pulls" alt="Docker pulls">
</a>

<a href="https://opal-access.slack.com/" target="_blank">
    <img src="https://img.shields.io/badge/Slack%20Community-4A154B?logo=slack&logoColor=white" alt="Join our Slack!">
</a>

## What is OPAL?
OPAL is an administration layer for <a href="https://www.openpolicyagent.org/">Open Policy Agent (OPA)</a>, detecting changes to both policy and policy data in realtime and pushing live updates to your agents. OPAL brings open-policy up to the speed needed by live applications.

As your application state changes (whether it's via your APIs, DBs, git, S3 or 3rd-party SaaS services), OPAL will make sure your services are always in sync with the authorization data and policy they need (and only those they need).

Check out our main site at <a href="https://opal.ac">OPAL.ac</a> and <a href="https://youtu.be/tG8jrdcc7Zo">this video</a> briefly explaining OPAL and how it works with OPA.

## Why use OPAL?
OPAL is the easiest way to keep your solution's authorization layer up-to-date in realtime. It aggregates policy and data from across the field and integrates them seamlessly into the authorization layer, and  is microservices and cloud-native.

## OPA + OPAL = 💜
While OPA (Open Policy Agent) decouples policy from code in a highly-performant and elegant way, the challenge of keeping policy agents up-to-date remains.
This is especially true in applications, where each user interaction or API call may affect access-control decisions.
OPAL runs in the background, supercharging policy-agents, keeping them in sync with events in realtime.

## Documentation

- 📃 &nbsp; [Full documentation is available here](docs/index.md)
- 💡 &nbsp; [Intro to OPAL](docs/intro.md)
- 🚀 &nbsp; Getting Started:

   OPAL is available both as **python packages** with a built-in CLI as well as pre-built **docker images** ready-to-go.

   - [Play with a live playground environment in docker-compose](docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md)
   <!-- - this tutorial is great for learning about OPAL core features and see what OPAL can do for you. -->
   - [Try the getting started guide for containers](docs/HOWTO/get_started_with_opal_using_docker.md)
   <!-- - this tutorial will show you how to configure OPAL to your specific needs and run the official docker containers locally or in production. -->

   - [Check out the Helm Chart for Kubernetes](https://github.com/permitio/opal-helm-chart)


   <br>

- 💪 &nbsp; TL;DR - This one command will download and run a working configuration of OPAL server and OPAL client on your machine:

```
curl -L https://raw.githubusercontent.com/permitio/opal/master/docker/docker-compose-example.yml \
> docker-compose.yml && docker-compose up
```
<p>
  <a href="https://asciinema.org/a/409288" target="_blank">
    <img src="https://asciinema.org/a/409288.svg" />
  </a>
</p>

- 🧠 &nbsp; "How-To"s

    - [How to get started with OPAL (Packages and CLI)](docs/HOWTO/get_started_with_opal_python_packages.md)

    - [How to get started with OPAL (Container Images)](docs/HOWTO/get_started_with_opal_using_docker.md)

    - [How to trigger Data Updates via OPAL](docs/HOWTO/trigger_data_updates.md)

    - [How to extend OPAL to fetch data from your sources with FetchProviders](docs/HOWTO/write_your_own_fetch_provider.md)

    - [How to configure OPAL (basic concepts)](docs/HOWTO/configure_opal.md)


- 🎨 &nbsp; [Key concepts and design](docs/design.md)
- 🏗️ &nbsp; [Architecture](docs/architecture.md)

    OPAL  uses a client-server stateless architecture. OPAL-Servers publish policy and data updates over a lightweight (websocket) PubSub Channel, which OPAL-clients subscribe to via topics. Upon updates each client fetches data directly (from source) to load it in to its managed OPA instance.
<br>
<br>

<img src="https://i.ibb.co/CvmX8rR/simplified-diagram-highlight.png" alt="simplified" border="0">



<br>


- 📖 &nbsp; For further reading check out our [Blog](https://bit.ly/opal_blog).

## Community

Come talk to us about OPAL, or authorization in general - we would love to hear from you ❤️

You can raise questions and ask for features to be added to the road-map in our [**Github discussions**](https://github.com/permitio/opal/discussions), report issues in [**Github issues**](https://github.com/permitio/opal/issues), follow us on Twitter to get the latest OPAL updates, and join our Slack community to chat about authorization, open-source, realtime communication, tech, or anything else!
</br>
</br>
If you are using our project, please consider giving us a ⭐️
</br>

[![Button][join-slack-link]][badge-slack-link] </br> [![Button][follow-twitter-link]][badge-twitter-link]

## Contributing to OPAL
- Pull requests are welcome! (please make sure to include *passing* tests and docs)
- Prior to submitting a PR - open an issue on GitHub, or make sure your PR addresses an existing issue well.

[join-slack-link]: https://i.ibb.co/wzrGHQL/Group-749.png
[badge-slack-link]: https://bit.ly/opalslack
[follow-twitter-link]: https://i.ibb.co/k4x55Lr/Group-750.png
[badge-twitter-link]: https://twitter.com/opal_ac

## There's more!
- Check out [OPToggles](https://github.com/permitio/OPToggles), which enables you to create user targeted feature flags/toggles based on Open Policy managed authorization rules!
