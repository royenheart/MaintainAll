#!/usr/bin/env python3
"""Patch hermes connector _conf_schema.json for hub mode."""
import json, os
p = '/AstrBot/data/plugins/astrbot_plugin_hermes_connector/_conf_schema.json'
with open(p) as f:
    schema = json.load(f)
schema['remote_mode']['default'] = 'hub'
schema['hub_endpoint']['default'] = 'http://hermes-api:8420'
schema['hub_verify_ssl']['default'] = False
schema['access_token']['default'] = os.environ.get('HERMES_ACCESS_TOKEN', '')
with open(p, 'w') as f:
    json.dump(schema, f, indent=2)
print('hermes connector: hub mode configured')
