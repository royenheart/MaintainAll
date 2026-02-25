#!/bin/bash

file=$1

prefix=/home/xiehz20/softwares
folder=x86-usr
filename=${file##*/}
filename=${filename%.*}

rpm2cpio ${file} > ${filename}.cpio
if lscpu | grep -wq aarch64
then
    if echo ${file} | grep -wq "x86_64"
    then
	echo "error! package not arm"
        exit -1	
    fi
    folder=arm-usr
else
    if echo ${file} | grep -wq "aarch64"
    then
	echo "error! package not x86_64"
    	exit -1
    fi
    folder=x86-usr
fi
mv ${filename}.cpio ${prefix}/${folder}
cd ${prefix}/${folder}
cpio -i --make-directories < ${filename}.cpio
