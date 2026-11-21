---
type: Project
title: "OpenVINO Intel Iris Xe Inference"
description: "Hardware iGPU embedding execution with capped CPU thread budget"
tags: [openvino, igpu, onnx, embeddings, throttling]
timestamp: 2026-10-06T10:00:00
---

# OpenVINO Intel Iris Xe Inference

Workstation embedding workloads offload ONNX matrix multiplication onto integrated Intel Iris Xe iGPU via `POWER_EMBED_DEVICE=auto` and OpenVINO execution provider.
CPU thread pools enforce `OMP_NUM_THREADS=4` and `POWER_EMBED_NUM_THREADS=4` so host throttling stays under 50 percent capacity.
