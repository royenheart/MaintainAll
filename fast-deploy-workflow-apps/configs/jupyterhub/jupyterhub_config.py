c = get_config()  #noqa
import os
from oauthenticator.generic import GenericOAuthenticator  # 使用通用认证器

# 使用 GenericOAuthenticator 来适配 Gitea
c.JupyterHub.authenticator_class = GenericOAuthenticator

# Gitea 实例的相关信息
GITEA_HOST = '你的Gitea域名或IP'  # 例如 'gitea.example.com' 或 'services-gitea'（Docker服务名）
GITEA_PORT = '3000'              # 与 docker-compose 中 Gitea 的端口映射一致
GITEA_URL = f'http://{GITEA_HOST}:{GITEA_PORT}'  # 如果使用反向代理或HTTPS，需调整

# 设置 OAuth 回调 URL，确保与在 Gitea 中注册的应用一致
# 此处使用 JupyterHub 的服务名和端口，或你的外部域名/IP
JUPYTERHUB_HOST = '你的JupyterHub域名或IP'  # 例如 'jupyterhub.example.com' 或 'localhost'
JUPYTERHUB_PORT = '8000'                    # 与 docker-compose 中 JupyterHub 的端口映射一致
c.GenericOAuthenticator.oauth_callback_url = f'http://{JUPYTERHUB_HOST}:{JUPYTERHUB_PORT}/hub/oauth_callback'

# Gitea 中注册应用后获取的客户端 ID 和密钥（需在Gitea界面创建应用后填写）
c.GenericOAuthenticator.client_id = '你的Gitea_OAuth_客户端ID'
c.GenericOAuthenticator.client_secret = '你的Gitea_OAuth_客户端密钥'

# Gitea 的 OAuth 端点配置
c.GenericOAuthenticator.authorize_url = f'{GITEA_URL}/login/oauth/authorize'
c.GenericOAuthenticator.token_url = f'{GITEA_URL}/login/oauth/access_token'
# 用户信息接口，使用 Gitea 的 /api/v1/user endpoint
c.GenericOAuthenticator.userdata_url = f'{GITEA_URL}/api/v1/user'
c.GenericOAuthenticator.userdata_method = 'GET'
c.GenericOAuthenticator.userdata_params = {'state': 'state'}
c.GenericOAuthenticator.scope = ['user:email', 'read:user'] # 请求的权限范围

# 定义如何从 Gitea 返回的用户信息中提取用户名
def gitea_user_info(resp):
    """
    处理 Gitea API 返回的用户信息，提取用户名。
    Gitea 的 /api/v1/user 返回的 JSON 中，用户名通常在 'login' 字段。
    """
    user_info = resp.json()
    # 建议首次调试时打印返回内容，以便确认数据结构
    # print("Gitea user info response:", user_info)
    return {
        'username': user_info.get('login'),  # 通常用户名在 'login' 字段
        'email': user_info.get('email', ''),  # 获取邮箱
        'name': user_info.get('full_name', user_info.get('login', '')),  # 获取全名或用户名
    }

c.GenericOAuthenticator.user_info = gitea_user_info
c.GenericOAuthenticator.username_key = 'username' # 设置用户名 key，用于 JupyterHub 识别用户

# 创建系统用户
c.GenericOAuthenticator.create_system_users = True

# 管理员用户和角色配置（根据你的需要修改）
c.JupyterHub.hub_connect_ip = 'services-jupyterhub' # 通常保持为服务名
c.JupyterHub.load_roles = [
    {
        "name": "admin",
        "users": ["你的Gitea管理员用户名"],  # 替换为 Gitea 中的管理员用户名
    }
]
c.Authenticator.admin_users = {'你的Gitea管理员用户名'}  # 替换为 Gitea 中的管理员用户名

# 用户访问控制（根据你的需要调整）
c.Authenticator.allow_all = True  # 如果设置为 True，则所有通过 Gitea 认证的用户都可以访问
# c.Authenticator.allow_existing_users = False  # 如果需要严格限制用户，可注释掉 allow_all 并使用 allowed_users
# c.Authenticator.allowed_users = {'允许的用户名1', '允许的用户名2'}  # 明确指定允许的用户集合

# 如果 Gitea 使用自签名证书，可能需要禁用 TLS 验证（通常在内网或不重要的情况下）
# import ssl
# ssl._create_default_https_context = ssl._create_unverified_context
# 或者设置环境变量（另一种方式）
# os.environ['OAUTH2_TLS_VERIFY'] = '0'
# os.environ['OAUTH_TLS_VERIFY'] = '0' :cite[1]
