#!/bin/sh

IFS="
"
for line in `cat userlist`; do
  test -z "$line" && continue
  user=`echo $line | cut -f 1 -d' '`
  echo "adding user $user"
  useradd -m -s /bin/bash $user
cat <<EOF | passwd $user
123456
123456
EOF
  # cp -r /srv/ipython/examples /home/$user/examples
  # chown -R $user /home/$user/examples
  chown -R $user:$user /home/$user
  chmod -R 700 /home/$user
done
