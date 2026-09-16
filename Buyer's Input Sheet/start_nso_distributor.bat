@echo off
title NSO Sales Plan Distributor
echo Starting NSO Sales Plan Distributor on http://localhost:8060 ...
echo Other users on the same network can access at http://<this-machine-ip>:8060
python nso_distributor.py
pause
