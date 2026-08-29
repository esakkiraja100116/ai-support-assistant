const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: "/ai-assistant-chat-demo",
  turbopack: {
    root: path.join(__dirname),
  },
  agentRules: false,
};

module.exports = nextConfig;
