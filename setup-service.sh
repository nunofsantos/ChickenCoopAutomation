#!/bin/bash
set -x

cp chickencoop.service /lib/systemd/system/chickencoop.service
chmod 644 /lib/systemd/system/chickencoop.service
mkdir -p /var/log/chickencoop
touch /var/log/chickencoop/coop.log
chown -R pi.pi /var/log/chickencoop
systemctl daemon-reload
systemctl enable chickencoop.service
systemctl start chickencoop.service
systemctl status chickencoop.service
