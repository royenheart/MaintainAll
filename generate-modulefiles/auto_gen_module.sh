#!/bin/bash

# debug
set -x

envFolder="${HOME}/envs"
apps=()

# use with example file moduleD and moduleD_Devel

function help() {
    echo "--out: specify the folder to locate the modulefiles"
    echo "  place this script in the softwares root folder and it will automatically find the softwares according to its name"
    echo "  please name the softwares with format <name-version>"
}

function find_files() {
    local path=$1
    local d=`ls ${path}`
    for file in ${d[@]}
    do
        if test -d ${path}/${file}
        then
            if [[ ! "${file}" =~ [a-zA-Z0-9_]+-([0-9]+\.)+[0-9]+ ]]; then
                echo "${file} not meets with the format name-version"
                exit -1
            fi
            # name
            apps[${#apps[*]}]=${file%-*}
            # version
            apps[${#apps[*]}]=${file#*-}
        fi
    done
}

## 读取参数
function read_config() {
    until [ $# -eq 0 ]
    do
        case $1 in
            "--out")
                shift
                envFolder=$1
                ;;
            "--help")
                help
                exit 0
                ;;
            *)
                echo "$1 options not recognized!"
                exit -1
                ;;
        esac
        shift
    done
}

read_config $@
find_files .

envFolder=$(cd ${envFolder} && pwd)
softdir=$(pwd)

for (( i=0;i<${#apps[@]};i=`expr ${i} + 2` ))
do
    name=${apps[${i}]}
    version=${apps[${i}+1]}
    fileFolder=${envFolder}/${name}
    software=${softdir}/${name}-${version}
    mkdir -p ${fileFolder}
    touch ${fileFolder}/${version}
    touch ${fileFolder}/${version}-devel
    
    cat ./moduleD > ${fileFolder}/${version}
    sed -i "s/SOFTWARES/${software//\//\\\/}/g" ${fileFolder}/${version}
    cat ./moduleD_Devel > ${fileFolder}/${version}-devel
    sed -i "s/SOFTWARES/${software//\//\\\/}/g" ${fileFolder}/${version}-devel
done