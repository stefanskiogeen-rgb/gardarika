#!/usr/bin/expect -f
set timeout 300
set password "SP129sGZFHNC"
set host "185.112.59.112"
set user "root"

spawn ssh $user@$host "docker logs --tail 20 gardarika_web"
expect {
    "*password:*" {
        send "$password\r"
    }
}
expect eof
