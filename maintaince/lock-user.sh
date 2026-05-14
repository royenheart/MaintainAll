#!/bin/bash

user=$1

sudo passwd -l $user
sudo usermod -s /sbin/nologin $user
sudo usermod -L $user
sudo pkill -kill -u $user
