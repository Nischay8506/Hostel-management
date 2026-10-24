"""AppSail, containers and conventional PaaS share the same startup entrypoint."""
import os
import uvicorn

if __name__ == '__main__':
    port = int(os.getenv('X_ZOHO_CATALYST_LISTEN_PORT') or os.getenv('PORT') or '8000')
    uvicorn.run('app.main:app', host='0.0.0.0', port=port, proxy_headers=True, access_log=False,
                forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS', '127.0.0.1'))
