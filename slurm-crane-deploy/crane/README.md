# How to use

```bash
apt install -y ansible
ansible-galaxy collection install community.general
ansible-playbook -i inventory.ini playbook.yml
```

# TODO

1. [ ] When upstream CraneSched config example changed, change templates also
2. [ ] Support more config params
3. [ ] Crane plugin install
4. [ ] Whether use ansible generate config or generate config with another tool
   For example: https://slurm.schedmd.com/configurator.html