#!/bin/bash

user=$1

if [[ $user == "" ]]; then
    echo "no (old/new) username specified"
else
    ps aux | awk '//{print $1,$2}' | grep ${user} | awk '//{print $2}' | xargs -I {} kill -9 {}
    unlink /home/${user}
    usermod -d /mnt/data1/users/$user -m $user
    userhome=$(cat /etc/passwd | grep ${user} | cut -d: -f6)
    ln -s $userhome /home/$user
fi