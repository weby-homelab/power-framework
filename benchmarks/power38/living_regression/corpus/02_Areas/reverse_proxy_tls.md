---
type: Area
title: "Reverse Proxy TLS Hardening"
description: "Nginx ingress proxy with TLS 1.3, HSTS headers, OCSP stapling, and automatic cert renewal"
tags: [nginx, tls, proxy, hsts, certificates]
timestamp: 2026-10-10T10:00:00
---

# Reverse Proxy TLS Hardening

Public ingress runs behind an Nginx reverse proxy terminating TLS 1.3 only, enforcing `Strict-Transport-Security` HSTS headers, OCSP stapling, and automated ACME certificate renewal hooks.
