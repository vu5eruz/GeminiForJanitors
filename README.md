<div align="center">
  <h3>GeminiForJanitors</h3>
  <p>Google AI Studio Proxy for JanitorAI</p>
</div>

<hr />

#### Running

Before you can run the proxy inside a local/development environment, you need to export the environmental variable `GFJPROXY_DEVELOPMENT` set to any non-empty value. Otherwise, the proxy will assume a cloud/production deployment and demand more configuration.

Any one of the following commands can be used to run the proxy. Running the proxy with `gunicorn` is the preferred way for a cloud/production deployment. Note that the code base assumes host 127.0.0.1 port number 5000, and thus it's not safe to specify other values.

```sh
flask --app gfjproxy.app run -h 127.0.0.1 -p 5000
gunicorn -b 127.0.0.1:5000 -k gevent -w 3 -t 65 gfjproxy.app.app
waitress-serve --listen=127.0.0.1:5000 gfjproxy.app.app
```

For local/development, you might want to get a trycloudflared link to use with JanitorAI. For that, export the path to the `cloudflared` executable in the environment variable `GFJPROXY_CLOUDFLARED`. The proxy will automatically get a tunnel that you can use with JanitorAI.
