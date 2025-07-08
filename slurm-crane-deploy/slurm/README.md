# deploy

- assume we have servers:

| IP            | hostname    |
| ------------- | ----------- |
| 192.168.1.163 | intern04-01 |
| 192.168.1.164 | intern04-02 |
| 192.168.1.165 | intern04-03 |
| 192.168.1.166 | intern04-04 |

- deploy: 

```bash
ansible-playbook -i inventory.ini playbook.yml
```