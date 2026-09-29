import type { NextConfig } from "next";

// NEXT_OUTPUT picks the build type:
//   standalone -> small Node server for the Docker image
//   export     -> plain static files for AWS Amplify (the page needs no server; all data comes from the API)
const output = process.env.NEXT_OUTPUT;

const nextConfig: NextConfig = {
  output: output === "standalone" || output === "export" ? output : undefined,
};

export default nextConfig;
