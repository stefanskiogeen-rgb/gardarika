#!/usr/bin/expect -f
set timeout 10
set ip "185.112.59.112"
set user "root"
set password "SP129sGZFHNC"

spawn ssh $user@$ip "cd /root/дизайн && docker-compose ps && ls -la"
expect {
    "*password:*" {
        send "$password\r"
    }
}
expect eof
