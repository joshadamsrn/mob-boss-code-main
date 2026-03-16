const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const BundleTracker = require("webpack-bundle-tracker");

module.exports = (_env, argv) => {
  const mode = argv.mode || "development";
  const isProd = mode === "production";

  return {
    mode,
    entry: {
      web: "./project/mobboss_apps/web/webpack/index.js",
      rooms_lobby: "./project/mobboss_apps/rooms/webpack/lobby.js",
    },
    output: {
      filename: isProd ? "[name]-[contenthash].js" : "[name].js",
      path: path.resolve(__dirname, "project/mobboss_apps/static/dist"),
      clean: true,
    },
    module: {
      rules: [
        {
          test: /\.css$/i,
          use: [MiniCssExtractPlugin.loader, "css-loader"],
        },
        {
          test: /\.(woff2?|eot|ttf|otf|svg)$/i,
          type: "asset/resource",
          generator: {
            filename: "assets/[name][ext]",
          },
        },
      ],
    },
    plugins: [
      new MiniCssExtractPlugin({
        filename: isProd ? "[name]-[contenthash].css" : "[name].css",
      }),
      new BundleTracker({
        path: path.resolve(__dirname, "project/mobboss_apps"),
        filename: "webpack-stats.json",
      }),
    ],
  };
};
