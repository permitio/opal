<p  align="center">
 <img src="https://i.ibb.co/BGVBmMK/opal.png" height=170 alt="opal" border="0" />
</p>
<h1 align="center">
⚡OPAL⚡
</h1>

<h2 align="center">
Open Policy Administration Layer 
</h2>

<a href="https://github.com/authorizon/opal/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/authorizon/opal/workflows/Tests/badge.svg" alt="Tests">
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

<a href="https://hub.docker.com/r/authorizon/opal-server" target="_blank">
    <img src="https://img.shields.io/docker/pulls/authorizon/opal-server?label=Docker%20pulls" alt="Docker pulls">
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
While OPA (Open Policy Agent) decouples policy from code in a highly-performant and elegant way, the challege of keeping policy agents up-to-date remains. 
This is especially true in applications, where each user interaction or API call may affect access-control decisions.
OPAL runs in the background, supercharging policy-agents, keeping them in sync with events in realtime.

## Documentation 
- To get started with OPAL, check out our [Getting Started guide](docs/HOWTO/get_started_with_opal.md).
- Full documentation is available at (link)
- For further tutorials check out [our blog](link)
- For an explanation on OPAL architecture see [Architecture deep-dive](docs/architecture.md) 

</br> 

<img src="https://i.ibb.co/CvmX8rR/simplified-diagram-highlight.png" alt="simplified" border="0">

</br> 

## Community

Come talk to us about OPAL, or authorization in general - we would love to hear from you ❤️

You can raise questions and ask for features to be added to the road-map in our [Github discussions](https://github.com/authorizon/opal/discussions), report issues in [Github issues](https://github.com/authorizon/opal/issues), 
and join our Slack community to chat about authorization, open-source, realtime communication, tech any anything else!
</br>
</br>
[![Button][join-slack-link]][badge-slack-link]

## Contributing to OPAL
- Pull requests are welcome! (please make sure to include *passing* tests and docs)
- Prior to submitting a PR - open an issue on GitHub, or make sure your PR addresses an existing issue well.  

[join-slack-link]: https://user-images.githubusercontent.com/282595/128394344-1bd9e5b2-e83d-4666-b446-2e4f431ffcea.png
[badge-slack-link]: https://bit.ly/opal-slack