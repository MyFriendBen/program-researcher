release: bash bin/fetch_sibling_files.sh
web: bash -c 'source bin/fetch_sibling_files.sh && gunicorn web.app:app --timeout 120'
worker: bash -c 'source bin/fetch_sibling_files.sh && rq worker -c web.rq_settings'
