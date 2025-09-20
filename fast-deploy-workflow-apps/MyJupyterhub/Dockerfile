FROM jupyterhub/jupyterhub:main

# Install oauthenticator from git
RUN pip install -i https://mirrors.cernet.edu.cn/pypi/web/simple oauthenticator jupyterhub jupyterlab jupyter traitlets

# Create oauthenticator directory and put necessary files in it
# RUN mkdir /srv/jupyterhub
WORKDIR /srv/jupyterhub
ADD UserAdd.sh /srv/jupyterhub/UserAdd.sh
ADD userlist /srv/jupyterhub/userlist
RUN chmod 700 /srv/jupyterhub

RUN ["sh", "/srv/jupyterhub/UserAdd.sh"]
