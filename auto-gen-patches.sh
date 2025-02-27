#!/bin/bash

# generate Patches

# SHELL调试
# set -x

root=$(pwd)
# 基准文件
default="${root}/default.mk"
# 补丁文件生成目录
patchf="${root}/patches"
files=$(ls ${root})

if ! test -d "${patchf}" 
then
    echo "no patches folder ${patchf} found! Now create one"
    mkdir -p ${patchf}
fi

for file in ${files[@]}
do
    if ! test -d ${file} && [[ ${file} =~ \.mk$ ]] && [[ ${file} != "$(basename ${default})" ]] ;
    then
        name=${file##*/}
        name=${name%.*}
        diff ${default} ${file} > ${patchf}/${name}.patch
    fi
done