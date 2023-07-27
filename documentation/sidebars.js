// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  opalSidebar: [
    {
      type: "doc",
      id: "welcome",
      label: "Welcome",
    },
    {
      type: "doc",
      id: "release-updates",
      label: "Release Updates",
    },
    {
      type: "category",
      label: "Getting Started",
      collapsible: false,
      collapsed: false,
      items: [
        {
          type: "doc",
          id: "getting-started/intro",
          label: "Introduction",
        },
        {
          type: "doc",
          id: "getting-started/tldr",
          label: "TL;DR",
        },
        {
          type: "category",
          label: "Quickstart",
          collapsible: true,
          collapsed: false,
          items: [
            {
              type: "category",
              label: "OPAL Playground",
              collapsible: true,
              collapsed: false,
              items: [
                {
                  type: "doc",
                  id: "getting-started/quickstart/opal-playground/overview",
                  label: "Overview",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/opal-playground/run-server-and-client",
                  label: "Run Server and Client",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/opal-playground/send-queries-to-opa",
                  label: "Send Queries to OPA",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/opal-playground/updating-the-policy",
                  label: "Updating the Policy",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/opal-playground/publishing-data-update",
                  label: "Publishing Data Updates",
                },
              ],
            },
            {
              type: "category",
              collapsible: true,
              label: "Docker Compose Config",
              items: [
                {
                  type: "doc",
                  id: "getting-started/quickstart/docker-compose-config/overview",
                  label: "Overview",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/docker-compose-config/postgres-database",
                  label: "Broadcast Channel",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/docker-compose-config/opal-client",
                  label: "OPAL Client",
                },
                {
                  type: "doc",
                  id: "getting-started/quickstart/docker-compose-config/opal-server",
                  label: "OPAL Server",
                },
              ],
            },
          ],
        },
        {
          type: "category",
          collapsible: true,
          collapsed: false,
          label: "Running OPAL",
          items: [
            // {
            //   type: "category",
            //   collapsible: true,
            //   label: "as Python Packages",
            //   items: [
            //     {
            //       type: "doc",
            //       id: "getting-started/running-opal/as-python-package/overview",
            //       label: "Overview",
            //     },
            //     {
            //       type: "doc",
            //       id: "getting-started/running-opal/as-python-package/opal-server-setup",
            //       label: "OPAL Server Setup",
            //     },
            //     {
            //       type: "doc",
            //       id: "getting-started/running-opal/as-python-package/opal-client-setup",
            //       label: "OPAL Client Setup",
            //     },
            //     {
            //       type: "doc",
            //       id: "getting-started/running-opal/as-python-package/running-in-prod",
            //       label: "Running in Production",
            //     },
            //     {
            //       type: "doc",
            //       id: "getting-started/running-opal/as-python-package/secure-mode-setup",
            //       label: "Secure Mode Setup",
            //     },
            //   ],
            // },

            {
              type: "doc",
              id: "getting-started/running-opal/overview",
              label: "Overview",
            },
            {
              type: "doc",
              id: "getting-started/running-opal/download-docker-images",
              label: "Download Docker Images",
            },
            {
              type: "doc",
              id: "getting-started/running-opal/run-docker-containers",
              label: "Run Docker Containers",
            },
            {
              type: "doc",
              id: "getting-started/running-opal/config-variables",
              label: "Configuration Variables",
            },
            {
              type: "category",
              collapsible: true,
              label: "Run OPAL Server",
              items: [
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/get-server-image",
                  label: "Get Server Image",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/broadcast-interface",
                  label: "Broadcast Interface",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/policy-repo-location",
                  label: "Policy Repo Location",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/policy-repo-syncing",
                  label: "Policy Repo Syncing",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/data-sources",
                  label: "Data Sources",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/security-parameters",
                  label: "Security Parameters",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-server/putting-all-together",
                  label: "Putting it All Together",
                },
              ],
            },
            {
              type: "category",
              collapsible: true,
              label: "Run OPAL Client",
              items: [
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/get-client-image",
                  label: "Get Client Image",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/obtain-jwt-token",
                  label: "Obtain JWT Token",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/server-uri",
                  label: "Server URI",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/data-topics",
                  label: "Data Topics",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/opa-runner-parameters",
                  label: "OPA Runner Parameters",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/standalone-opa-uri",
                  label: "Standalone OPA URI",
                },
                {
                  type: "doc",
                  id: "getting-started/running-opal/run-opal-client/lets-run-the-client",
                  label: "Let's Run the Client",
                },
              ],
            },
            {
              type: "doc",
              id: "getting-started/running-opal/troubleshooting",
              label: "Troubleshooting",
            },
          ],
        },
        {
          type: "doc",
          id: "getting-started/configuration",
          label: "Configuration",
        },
      ],
    },
    {
      type: "category",
      label: "OPAL Basics",
      collapsible: false,
      collapsed: false,
      items: [
        {
          type: "autogenerated",
          dirName: "overview",
        },
      ],
    },
    {
      type: "category",
      label: "Tutorials",
      collapsed: false,
      items: [
        {
          type: "autogenerated",
          dirName: "tutorials",
        },
      ],
    },
    {
      type: "doc",
      id: "fetch-providers",
      label: "Fetch Providers",
    },
    {
      type: "doc",
      id: "FAQ",
      label: "FAQ",
    },
    {
      type: "doc",
      id: "OPAL_PLUS",
      label: "OPAL + (Extended OPAL License)",
    },
  ],
};

module.exports = sidebars;
