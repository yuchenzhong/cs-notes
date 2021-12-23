#!/bin/bash

NNODES=4
NPROC_PER_NODE=1
MASTER_IP=172.30.2.12
MASTER_PORT=1234

python3 -m torch.distributed.run \
	--nnodes=$NNODES --nproc_per_node=$NPROC_PER_NODE \
	--rdzv_id=1234 --rdzv_backend=c10d \
	--rdzv_endpoint=$MASTER_IP \
	main.py