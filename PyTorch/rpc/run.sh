#!/bin/bash

NNODES=2
NPROC_PER_NODE=1
MASTER_IP=172.31.19.28

export NCCL_SOCKET_IFNAME=ens5

cmd="python3 -m torch.distributed.run \
	--nnodes=$NNODES --nproc_per_node=$NPROC_PER_NODE \
	--rdzv_id=1234 --rdzv_backend=c10d \
	--rdzv_endpoint=$MASTER_IP \
	main.py"

LOGLEVEL=DEBUG NCCL_DEBUG=INFO exec $cmd
