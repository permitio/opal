<p  align="center">
 <img src="https://github.com/permitio/opal/assets/4082578/4e21f85f-30ab-43e2-92de-b82f78888c71" height=170 alt="opal" border="0" />
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
    <img src="https://static.pepy.tech/personalized-badge/opal-client?period=total&units=international_system&left_color=black&right_color=blue&left_text=Downloads" alt="Downloads">
</a>

<a href="https://hub.docker.com/r/permitio/opal-server" target="_blank">
    <img src="https://img.shields.io/docker/pulls/permitio/opal-client?label=Docker%20pulls" alt="Docker pulls">
</a>

<a href="https://bit.ly/permit-slack" target="_blank">
    <img src="https://img.shields.io/badge/Slack%20Community-4A154B?logo=slack&logoColor=white" alt="Join our Slack!">
</a>
<a href="https://twitter.com/intent/follow?original_referer=https%3A%2F%2Fpublish.twitter.com%2F%3FbuttonType%3DFollowButton%26query%3Dhttps%253A%252F%252Ftwitter.com%252Fpermit_io%26widget%3DButton&ref_src=twsrc%5Etfw&region=follow_link&screen_name=permit_io&tw_p=followbutton"><img src="https://img.shields.io/twitter/follow/permit_io?label=Follow%20%40permit_io&style=social">
</a>

## What is OPAL?

OPAL is an administration layer for Policy Engines such as <a target="_blank" href="https://www.openpolicyagent.org/">Open Policy Agent (OPA)</a>, and <a target="_blank" href="https://github.com/permitio/cedar-agent">AWS' Cedar Agent</a> detecting changes to both policy and policy data in realtime and pushing live updates to your agents. OPAL brings open-policy up to the speed needed by live applications.

As your application state changes (whether it's via your APIs, DBs, git, S3 or 3rd-party SaaS services), OPAL will make sure your services are always in sync with the authorization data and policy they need (and only those they need).

Check out our main site at <a target="_blank" href="https://opal.ac">OPAL.ac</a>, <a target="_blank" href="https://youtu.be/tG8jrdcc7Zo">this video</a> briefly explaining OPAL and how it works with OPA, and a deeper dive into it at [this OWASP DevSlop talk](https://www.youtube.com/watch?v=1_Iz0tRQCH4).

## Why use OPAL?

OPAL is the easiest way to keep your solution's authorization layer up-to-date in realtime. It aggregates policy and data from across the field and integrates them seamlessly into the authorization layer, and is microservices and cloud-native.

## OPA + OPAL == 💜

While OPA (Open Policy Agent) decouples policy from code in a highly-performant and elegant way, the challenge of keeping policy agents up-to-date remains.
This is especially true in applications, where each user interaction or API call may affect access-control decisions.
OPAL runs in the background, supercharging policy-agents, keeping them in sync with events in realtime.

## AWS Cedar + OPAL == 💪

Cedar is a very powerful policy language, which powers AWS' AVP (Amazon Verified Permissions) - but what if you want to enjoy the power of Cedar on another cloud, locally, or on premise?
This is where [Cedar-Agent](https://github.com/permitio/cedar-agent) and OPAL come in.

## Documentation

- 📃 &nbsp; [Full documentation is available here](https://docs.opal.ac)
- 💡 &nbsp; [Intro to OPAL](https://docs.opal.ac/getting-started/intro)
- 🚀 &nbsp; Getting Started:

  OPAL is available both as **python packages** with a built-in CLI as well as pre-built **docker images** ready-to-go.

  - [Play with a live playground environment in docker-compose](https://docs.opal.ac/getting-started/quickstart/opal-playground/overview)
  <!-- - this tutorial is great for learning about OPAL core features and see what OPAL can do for you. -->
  - [Try the getting started guide for containers](https://docs.opal.ac/getting-started/running-opal/overview)
  <!-- - this tutorial will show you how to configure OPAL to your specific needs and run the official docker containers locally or in production. -->

  - [Check out the Helm Chart for Kubernetes](https://github.com/permitio/opal-helm-chart)

- A video demo of OPAL is available [here](https://www.youtube.com/watch?v=IkR6EGY3QfM)

- You can also check out this webinar and Q&A about OPAL [on our YouTube channel](https://www.youtube.com/watch?v=A5adHlkmdC0&t=1s)
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

  - [How to get started with OPAL (Packages and CLI)](https://docs.opal.ac/getting-started/running-opal/as-python-package/overview)

  - [How to get started with OPAL (Container Images)](https://docs.opal.ac/getting-started/running-opal/overview)

  - [How to trigger Data Updates via OPAL](https://docs.opal.ac/tutorials/trigger_data_updates)

  - [How to extend OPAL to fetch data from your sources with FetchProviders](https://docs.opal.ac/tutorials/write_your_own_fetch_provider)

  - [How to configure OPAL (basic concepts)](https://docs.opal.ac/tutorials/configure_opal)

  - [How to Use OPAL with Cedar in a Multi-Language Project](https://www.permit.io/blog/scaling-authorization-with-cedar-and-opal)

- 🎨 &nbsp; [Key concepts and design](https://docs.opal.ac/overview/design)
- 🏗️ &nbsp; [Architecture](https://docs.opal.ac/overview/architecture)
<be>
<br>
OPAL  uses a client-server stateless architecture. OPAL-Servers publish policy and data updates over a lightweight (websocket) PubSub Channel, which OPAL-clients subscribe to via topics. Upon updates each client fetches data directly (from source) to load it in to its managed OPA instance.
  <br>
<img src="https://github.com/permitio/opal/assets/4082578/99d3dd95-a7ff-45c2-805e-3d533f8b1e8c" alt="simplified" border="0">
<br>
📖 &nbsp; For further reading check out our [Blog](https://bit.ly/opal_blog).

## Community

Come talk to us about OPAL, or authorization in general - we would love to hear from you ❤️

You can raise questions and ask for features to be added to the road-map in our [**Github discussions**](https://github.com/permitio/opal/discussions), report issues in [**Github issues**](https://github.com/permitio/opal/issues), follow us on Twitter to get the latest OPAL updates, and join our Slack community to chat about authorization, open-source, realtime communication, tech, or anything else!
</br>
</br>
If you are using our project, please consider giving us a ⭐️
</br>

[![Button][join-slack-link]][badge-slack-link] </br> [![Button][follow-twitter-link]][badge-twitter-link]

## Contributing to OPAL

- Pull requests are welcome! (please make sure to include _passing_ tests and docs)
- Prior to submitting a PR - open an issue on GitHub, or make sure your PR addresses an existing issue well.

[join-slack-link]: https://i.ibb.co/wzrGHQL/Group-749.png
[badge-slack-link]: https://io.permit.io/join_community
[follow-twitter-link]: https://i.ibb.co/k4x55Lr/Group-750.png
[badge-twitter-link]: https://twitter.com/opal_ac

## There's more!

- Check out [OPToggles](https://github.com/permitio/OPToggles), which enables you to create user targeted feature flags/toggles based on Open Policy managed authorization rules!
- Check out [Cedar-Agent](https://github.com/permitio/cedar-agent), the easiest way to deploy & run AWS Cedar.
