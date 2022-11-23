// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion

const lightCodeTheme = require("./src/css/prism-theme");
const darkCodeTheme = require("prism-react-renderer/themes/dracula");

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "OPAL",
  tagline: "Administration layer for the Open Policy Agent",
  url: "https://docs.opal.ac",
  baseUrl: "/",
  onBrokenLinks: "throw",
  onBrokenMarkdownLinks: "warn",
  favicon: "img/favicon.ico",
  organizationName: "permitio", // Usually your GitHub org/user name.
  projectName: "opal", // Usually your repo name.

  // Even if you don't use internalization, you can use this field to set useful
  // metadata like html lang. For example, if your site is Chinese, you may want
  // to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: require.resolve("./sidebars.js"),
          routeBasePath: "/",
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
        },
        blog: false, // disabled docusaurus default blog
        theme: {
          customCss: require.resolve("./src/css/custom.scss"),
        },
      }),
    ],
  ],

  plugins: ["docusaurus-plugin-sass"],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: "OPAL",
        logo: {
          alt: "My Site Logo",
          src: "img/opal.png",
        },
        items: [
          {
            href: "https://github.com/permitio/opal",
            label: "GitHub",
            position: "right",
          },
        ],
      },
      footer: {
        style: "dark",
        links: [
          {
            label: "Visit Permit.io",
            to: "https://permit.io",
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} Permit, Inc.`,
      },
      prism: {
        theme: require("prism-react-renderer/themes/nightOwl"),
        // darkTheme: require("prism-react-renderer/themes/nightOwlLight"),
      },
      announcementBar: {
        id: "support_us",
        content:
          'If you like OPAL, give us a ⭐️ on <a href="https://www.github.com/permitio/opal" target="_blank" rel="noopener noreferrer">GitHub</a> and follow us on <a href="https://www.twitter.com/permit_io" target="_blank" rel="noopener noreferrer">Twitter</a>',
        backgroundColor: "#6851ff",
        textColor: "#FFFFFF",
        isCloseable: true,
      },
    }),
};

module.exports = config;
