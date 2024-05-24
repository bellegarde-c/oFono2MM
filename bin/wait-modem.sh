#!/bin/bash
while true
do
	gdbus call -y -d org.ofono -o / -m org.ofono.Manager.GetModems | grep ril_0 >/dev/null && break
done
