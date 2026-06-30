#!/usr/bin/env python3
"""Patch HAPI connector _conf_schema.json — default to host Codex."""
import json
p = '/AstrBot/data/plugins/astrbot_plugin_hapi_connector/_conf_schema.json'
with open(p) as f:
    schema = json.load(f)
schema['hapi_endpoint']['default'] = 'http://host.docker.internal:3006'
with open(p, 'w') as f:
    json.dump(schema, f, indent=2)
print('hapi connector: host.docker.internal:3006')
