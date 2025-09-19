c = get_config()  #noqa
import os
from oauthenticator.gitlab import LocalGitLabOAuthenticator
c.JupyterHub.authenticator_class = LocalGitLabOAuthenticator
c.LocalGitLabOAuthenticator.create_system_users = True
GITLAB_HOST = 'xxx:port'
GITLAB_URL = 'http://xxx:port'
os.environ['GITLAB_HOST'] = GITLAB_HOST
os.environ['GITLAB_URL'] = GITLAB_URL
c.OAuthenticator.oauth_callback_url = "http://xxx:port/hub/oauth_callback"
c.OAuthenticator.client_id = "xxx"
c.OAuthenticator.client_secret = "xxx"
c.JupyterHub.hub_connect_ip = 'services-jupyterhub'
c.JupyterHub.load_roles = [
    {
        "name": "admin",
        "users": ["xxxx"],
    }
]
c.Authenticator.admin_users = {'xxx'}
c.Authenticator.allow_all = True
c.Authenticator.allow_existing_users = False
c.Authenticator.allowed_users = {'xxx'}
