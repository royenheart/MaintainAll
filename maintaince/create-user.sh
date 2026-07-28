#!/bin/bash

set -ex

user=$1

if [[ $user == "" ]]; then
    echo "no username specified"
else
    useradd -s /bin/bash -m $user
    hashed_pass=$(openssl passwd -6 "${user}")
    usermod -p "$hashed_pass" $user
    chage -d 0 $user
fi
