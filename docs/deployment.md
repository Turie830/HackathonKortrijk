# Deploy the demo to Google Cloud Run

The app includes a Dockerfile for Google Cloud Run. Open Cloud Shell, clone the
repository (branch `main`) and run these commands in the directory containing
the Dockerfile and app.py:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy parallax \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --max-instances 1 \
  --concurrency 1 \
  --set-env-vars 'PARALLAX_ALLOWED_HOSTS=*.run.app,PARALLAX_ADMIN_PASSWORD=choose-a-team-password,PARALLAX_DEMO_PASSWORD=choose-another-password'
```

Cloud Run builds the Dockerfile and prints a Service URL. Open that HTTPS URL.

## Logging in online

- `admin` logs in with the value of `PARALLAX_ADMIN_PASSWORD` and can switch
  between the demo perspectives (consultant Sara, source owner An, knowledge
  manager Kim) at the top right.
- `sara`, `an` and `kim` log in with the value of `PARALLAX_DEMO_PASSWORD`.
- The empty admin password only works on a developer's own machine (localhost).
  It is switched off in the image (`PARALLAX_DEMO_ADMIN=0`) and never works through
  Cloud Run's proxy.

Choose the passwords at deploy time and share them only with the team. They are
not stored in the repository. Do not use commas in them, because
`--set-env-vars` separates variables with commas. To change a password later
without rebuilding:

```bash
gcloud run services update parallax --region europe-west1 --update-env-vars PARALLAX_ADMIN_PASSWORD=new-team-password
```

For a stricter setup, store the passwords in Secret Manager and pass them with
`--set-secrets` instead of `--set-env-vars`.

## What the image configures

- `FORWARDED_ALLOW_IPS=*`: Cloud Run's managed ingress is the only way in, so
  Uvicorn trusts its forwarded headers and recognises HTTPS. The secure cookies
  and the same-origin checks need that. Do not use this setting outside such a proxy.
- `PARALLAX_SECURE_COOKIES=1`: session cookies are only sent over HTTPS.
- `PARALLAX_DEMO_CONTROLS=1`: the knowledge manager can simulate a month and
  reset the demo. Set it to `0` to hide those controls.
- `PARALLAX_ALLOWED_HOSTS`: enables Cloud Run hostnames while keeping localhost
  enabled for development. For a custom domain, add its hostname.

## Limits

The image contains the seed sources, not your local SQLite database or
environment files. On the first request the app builds the fictitious demo
history (about a second). Cloud Run's filesystem is temporary: reviews, new
versions and simulated months disappear when an instance stops or a new
revision starts. One instance and concurrency one avoid SQLite concurrency
issues; they do not provide durable storage. Production use would need a
persistent database and single sign-on. A lab project may also be removed when
the lab ends.

If deployment reports a permissions error, check the build log. Source deployments
require deployer permissions and a build service account with Cloud Run Builder.
Have the project administrator grant the permissions described in Google's guide.

References:

- [Cloud Run source deployment](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run container contract and temporary filesystem](https://docs.cloud.google.com/run/docs/container-contract)
- [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
