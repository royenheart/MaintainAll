#!/bin/bash

user=$1

if [[ $user == "" ]]; then
    echo "no username specified"
else
    useradd -m $1
    echo "$1" | passwd --stdin $1
    chage -d 0 $1
fi