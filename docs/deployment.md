# Deploy the demo to Google Cloud Run

The app includes a Dockerfile for Google Cloud Run. Upload the current project
files to Cloud Shell, or clone the repository after committing and pushing the
deployment files and current app changes. Run these commands in the directory
containing the Dockerfile and app.py:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy parallax \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --max-instances 1 \
  --concurrency 1 \
  --set-env-vars 'PARALLAX_ALLOWED_HOSTS=*.run.app,FORWARDED_ALLOW_IPS=*'
```

Cloud Run builds the Dockerfile and prints a Service URL. Open that HTTPS URL.
The deployment is public: anyone with the URL can view and change demo reviews.
Use fictitious data only; this version has no accounts or tenant isolation.

`PARALLAX_ALLOWED_HOSTS` enables Cloud Run hostnames while keeping localhost
enabled for development. For a custom domain, add its hostname to that variable.
`FORWARDED_ALLOW_IPS=*` is for Cloud Run's managed ingress proxy. It allows
Uvicorn to recognise HTTPS so the same-origin checks accept browser requests.
Use this setting only behind trusted ingress; leave it unset for local use.

The image contains only the seed sources, not your local SQLite database or
environment files. Cloud Run's filesystem is temporary. Reviews, decisions and
answer snapshots can disappear when an instance stops or a new revision starts.
One instance and concurrency one reduce SQLite concurrency issues; they do not
provide durable storage. Production use needs persistent database storage and
authentication. A lab project may also be removed when the lab ends.

If deployment reports a permissions error, check the build log. Source deployments
require deployer permissions and a build service account with Cloud Run Builder.
Have the project administrator grant the permissions described in Google's guide.

References:

- [Cloud Run source deployment](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run container contract and temporary filesystem](https://docs.cloud.google.com/run/docs/container-contract)
- [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)

This configuration has been prepared locally. It has not been deployed to Google
Cloud or verified there.
