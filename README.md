<div align="center">
  <img src="gfjproxy/static/gfjproxy.png" alt="Logo" />
  <h3>GeminiForJanitors</h3>
  <p>Google AI Studio Proxy for JanitorAI</p>
</div>

<hr />

#### Running (for Developers)

Before you can run the proxy inside a local/development environment, you need to export the environmental variable `GFJPROXY_DEVELOPMENT` set to any non-empty value. Otherwise, the proxy will assume a cloud/production deployment and demand more configuration.

Any one of the following commands can be used to run the proxy. Running the proxy with `gunicorn` is the preferred way for a cloud/production deployment. Note that the code base assumes host 127.0.0.1 port number 5000, and thus it's not safe to specify other values.

```sh
flask --app gfjproxy.app run -h 127.0.0.1 -p 5000
gunicorn -b 127.0.0.1:5000 -k gevent -w 3 -t 65 gfjproxy.app
waitress-serve --listen=127.0.0.1:5000 gfjproxy.app.app
```

For local/development, you might want to get a trycloudflared link to use with JanitorAI. For that, export the path to the `cloudflared` executable in the environment variable `GFJPROXY_CLOUDFLARED`. The proxy will automatically get a tunnel that you can use with JanitorAI.

#### Deploying on Render

You must first create a Render account, bound to a monthly 100 GB bandwidth quota if you use the free tier, with which you will be able to host one proxy instance. If you see this screen after signing in, press **Skip**.

<img src="gfjproxy/images/render-1.png" />

You should make it to your dashboard or workspace page, then go to the **Blueprints** tab.

<img src="gfjproxy/images/render-2.png" />

Once you are in the New Blueprint page, copy-paste https://github.com/vu5eruz/GeminiForJanitors into the **Public Git Repository** field and press **Continue**.

<img src="gfjproxy/images/render-3.png" />

Put "gfjproxy" (without quotes) into **Blueprint Name**. Put your contacts into the value of **GFJPROXY_ADMIN**, such as your Discord or JanitorAI handles or just your name, otherwise your proxy will say it is hosted by `@undefinedundefined` from JanitorAI.

<img src="gfjproxy/images/render-4.png" />

With this, your proxy should be up and running shortly. If you go back to your dashboard/workspace, you can click on **GeminiForJanitors** (not to be confused with *GeminiForJanitors-redis*) and see your URL, as well as have access to the proxy's Logs and Metrics tabs.

<img src="gfjproxy/images/render-5.png" />

Use the Logs tab to see how people use your proxy. Use the Metrics tab to see how much bandwidth has been used. Optionally, you may want to change the default cooldown value from 60 seconds to something else or set it zero to disable it; for that, go to the Environment tab and change the value of GFJPROXY_COOLDOWN.

<img src="gfjproxy/images/render-6.png" />
