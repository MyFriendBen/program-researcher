# Deploying Program Researcher to Heroku

## 1. Create the Heroku app with buildpacks

```bash
heroku create mfb-program-researcher --team your-team-name
heroku buildpacks:add heroku-community/apt
heroku buildpacks:add heroku/python
```

The APT buildpack installs `poppler-utils` for PDF processing. Order matters — APT must come before Python.

## 2. Add Redis

```bash
heroku addons:create heroku-redis:mini
```

This sets `REDIS_URL` automatically. It powers the job queue between the web and worker dynos.

## 3. Create a Gmail app password for email delivery

Go to the Google Workspace admin (or the Gmail account you want to send from):

1. Open [myaccount.google.com](https://myaccount.google.com) > Security > 2-Step Verification
2. At the bottom, click **App passwords**
3. Create one for "Mail" — you'll get a 16-character password like `abcd-efgh-ijkl-mnop`

You'll use this in the next step.

## 4. Set SMTP credentials

```bash
heroku config:set SMTP_USER=researcher@myfriendben.org
heroku config:set SMTP_PASSWORD=abcd-efgh-ijkl-mnop
heroku config:set EMAIL_FROM=researcher@myfriendben.org
```

Replace the password with the app password from step 3. `SMTP_USER` and `EMAIL_FROM` can be any Google Workspace address in your org.

## 5. Set API keys and secrets

```bash
heroku config:set RESEARCH_AGENT_ANTHROPIC_API_KEY=sk-ant-...
heroku config:set SECRET_KEY=$(openssl rand -hex 32)
heroku config:set APP_PASSWORD=your-team-password
```

The Anthropic key is required. `APP_PASSWORD` gates access to the web form — share it with your team. Leave it blank to skip auth entirely.

## 6. Set the org email list (optional)

```bash
heroku config:set ORG_EMAILS="elliott@myfriendben.org,alice@myfriendben.org"
```

This shows a dropdown on the form instead of a freeform email field. Skip this if you'd rather let people type their own.

## 7. Deploy

```bash
git push heroku main
heroku ps:scale web=1 worker=1
```

Both dynos are needed — web serves the form, worker runs the research jobs in the background.

## 8. Verify

```bash
heroku open
heroku logs --tail
```

Open the form, submit a test run with a small program, and check your email in 5–10 minutes.
