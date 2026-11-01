module.exports = {
  devServer: {
    host: "0.0.0.0",
    port: 8080,
    disableHostCheck: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true
      },
      "/socket.io": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
        ws: true
      }
    }
  },
  lintOnSave: undefined,
  runtimeCompiler: true
};
