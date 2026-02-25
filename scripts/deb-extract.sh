#!/bin/bash

file=$1
folder=$(cd $2 && pwd)

dpkg -X ${file} ${folder}
