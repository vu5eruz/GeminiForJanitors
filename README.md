<div align="center">
  <h3>GeminiForJanitors</h3>
  <p>Google AI Studio Proxy for JanitorAI</p>
</div>

## Running

Before you can run the proxy inside a local/development environment, you need to export the environmental variable `GEMINIFORJANITORS_DEVELOPMENT` set to any non-empty value. Otherwise, the proxy will assume a cloud/production deployment and demand more configuration. Any of the following commands can be used to run the proxy.

```sh
flask run -h 127.0.0.1 -p 5000
gunicorn -b 127.0.0.1:5000 -k gevent -w 3 -t 65 app:app
waitress-serve --listen=127.0.0.1:5000 app:app
```
