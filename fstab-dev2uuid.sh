#!/bin/bash

#back up first
cp /etc/fstab /etc/fstab.back

devLists=`cat /etc/fstab | grep /dev/sd | awk '{print $1}'`
for dev in ${devLists}
do 
    uuid=`lsblk ${dev} -o uuid | grep -v UUID`    
    dev=${dev//\//\\/}
    sed -i 's/'"$dev"'/UUID='"$uuid"'/g' /etc/fstab
done
