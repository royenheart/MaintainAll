#!/bin/bash

srunconfig=$1
frpconfig=$2

ping -c 2 baidu.com > /dev/null 2>&1

# If not connected
if [ $? -ne 0 ]; then
    /opt/srun-login-cli/srun login -c $srunconfig
    if [ $? -ne 0 ]; then
        echo "srun connect failed"
        exit 1
    fi
fi

# Execute frpc to connect to outer
/opt/frp/frpc -c $frpconfig