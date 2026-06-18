# Deploying Program Researcher

Assumes the app is already set up. See `SETUP.md` for first-time setup.

Requires `benefits-api` and `benefits-calculator` to be checked out as sibling directories.

## 1. Deploy

```bash
bash bin/deploy.sh
```

This copies `screener/models.py` and `FormData.ts` from your local sibling repos into `vendor/sibling_files/`, pushes to Heroku, then removes them from your working tree.

## 2. Scale dynos (first deploy only, or if dynos were stopped)

```bash
heroku ps:scale web=1 worker=1 --app mfb-program-researcher
```

## 3. Verify

```bash
heroku open --app mfb-program-researcher
heroku logs --tail --app mfb-program-researcher
```

Open the form, submit a test run with a small program, and check your email in 5–10 minutes.
