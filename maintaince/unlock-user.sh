#!/bin/bash

user=$1

sudo passwd -u $user
sudo usermod -s /bin/bash $user
sudo usermod -U $user
