# jupyterhub_config.py
c = get_config()  # noqa
import os
import pwd
import grp
import subprocess
from oauthenticator.generic import GenericOAuthenticator
from traitlets import Bool, Integer


class CustomGiteaOAuthenticator(GenericOAuthenticator):
    """
    自定义 Gitea OAuth 认证器，支持自动创建系统用户
    """

    create_system_users = Bool(
        True,
        help="""Create system users that do not exist yet when a user logs in for the first time.""",
    ).tag(config=True)

    user_uid_start = Integer(2000, help="""Starting UID for created users""").tag(
        config=True
    )

    user_gid = Integer(100, help="""GID for created users""").tag(  # users group
        config=True
    )

    def _get_next_uid(self):
        """获取下一个可用的 UID"""
        uid = self.user_uid_start
        while True:
            try:
                pwd.getpwuid(uid)
                uid += 1
            except KeyError:
                return uid

    def _create_system_user(self, username):
        """创建系统用户"""
        try:
            # 检查用户是否已存在
            pwd.getpwnam(username)
            self.log.info(f"User {username} already exists")
            return True
        except KeyError:
            pass

        if not self.create_system_users:
            self.log.error(
                f"User {username} does not exist and create_system_users is False"
            )
            return False

        try:
            uid = self._get_next_uid()
            home_dir = f"/home/{username}"

            # 创建用户
            cmd = [
                "useradd",
                "--create-home",
                "--home-dir",
                home_dir,
                "--shell",
                "/bin/bash",
                "--uid",
                str(uid),
                "--gid",
                str(self.user_gid),
                username,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.log.info(f"Created system user {username} with UID {uid}")

            # 设置家目录权限
            os.chmod(home_dir, 0o755)
            os.chown(home_dir, uid, self.user_gid)

            return True

        except subprocess.CalledProcessError as e:
            self.log.error(f"Failed to create user {username}: {e.stderr}")
            return False
        except Exception as e:
            self.log.error(f"Error creating user {username}: {str(e)}")
            return False

    async def authenticate(self, handler, data=None):
        """重写认证方法，在认证成功后创建用户"""
        # 先进行 OAuth 认证
        user_info = await super().authenticate(handler, data)

        if user_info:
            username = user_info["name"]
            # 认证成功后创建系统用户
            if not self._create_system_user(username):
                self.log.error(
                    f"Authentication succeeded but failed to create system user for {username}"
                )
                return None

        return user_info


# 使用自定义认证器
c.JupyterHub.authenticator_class = CustomGiteaOAuthenticator

# Gitea 实例的相关信息
GITEA_HOST = "services-gitea"  # Docker 服务名
GITEA_PORT = "3000"
GITEA_URL = f"http://{GITEA_HOST}:{GITEA_PORT}"

# JupyterHub 配置
JUPYTERHUB_HOST = "localhost"  # 外部访问地址
JUPYTERHUB_PORT = "8000"
c.CustomGiteaOAuthenticator.oauth_callback_url = (
    f"http://{JUPYTERHUB_HOST}:{JUPYTERHUB_PORT}/hub/oauth_callback"
)

# OAuth 配置 - 请替换为你的实际值
c.CustomGiteaOAuthenticator.client_id = "your-gitea-oauth-client-id"
c.CustomGiteaOAuthenticator.client_secret = "your-gitea-oauth-client-secret"

# Gitea OAuth 端点
c.CustomGiteaOAuthenticator.authorize_url = f"{GITEA_URL}/login/oauth/authorize"
c.CustomGiteaOAuthenticator.token_url = f"{GITEA_URL}/login/oauth/access_token"
c.CustomGiteaOAuthenticator.userdata_url = f"{GITEA_URL}/api/v1/user"
c.CustomGiteaOAuthenticator.userdata_method = "GET"
c.CustomGiteaOAuthenticator.userdata_params = {"state": "state"}
c.CustomGiteaOAuthenticator.scope = ["user:email", "read:user"]


# 用户信息处理函数
def gitea_user_info(resp):
    user_info = resp.json()
    return {
        "username": user_info.get("login"),
        "email": user_info.get("email", ""),
        "name": user_info.get("full_name", user_info.get("login", "")),
    }


c.CustomGiteaOAuthenticator.user_info = gitea_user_info
c.CustomGiteaOAuthenticator.username_key = "username"

# 创建系统用户配置
c.CustomGiteaOAuthenticator.create_system_users = True
c.CustomGiteaOAuthenticator.user_uid_start = 2000  # 起始 UID
c.CustomGiteaOAuthenticator.user_gid = 100  # 用户组 GID

# JupyterHub 基本配置
c.JupyterHub.hub_connect_ip = "services-jupyterhub"

# 管理员配置
c.JupyterHub.load_roles = [
    {
        "name": "admin",
        "users": ["your-gitea-admin-username"],  # 替换为实际管理员用户名
    }
]
c.Authenticator.admin_users = {"your-gitea-admin-username"}

# 用户访问控制
c.Authenticator.allow_all = True

# 调试配置（可选）
c.JupyterHub.log_level = "DEBUG"
c.Authenticator.log_level = "DEBUG"
