import argparse
import os
import random
import sys
import time
from datetime import timedelta

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms

from model import PipelineParallelResNet50
from schedule import (initialize_global_args, is_pipeline_last_stage,
                      pipedream_flush_schedule)

parser = argparse.ArgumentParser(
    description='Pipeline Parallel ResNet50 Arguments')
parser.add_argument('data', metavar='DIR', help='path to dataset')
parser.add_argument('-j', '--workers', default=4, type=int, metavar='N',
                    help='number of data loading workers (default: 4)')
parser.add_argument('--epochs', default=90, type=int, metavar='N',
                    help='number of total epochs to run')
parser.add_argument('--lr', '--learning-rate', default=0.1, type=float,
                    metavar='LR', help='initial learning rate', dest='lr')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--wd', '--weight-decay', default=1e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)',
                    dest='weight_decay')
parser.add_argument('-p', '--print-freq', default=10, type=int,
                    metavar='N', help='print frequency (default: 10)')
parser.add_argument('--seed', default=None, type=int,
                    help='seed for initializing training. ')
parser.add_argument('--benchmark-iters', default=100, type=int, metavar='N',
                    help='number of total iterations to run for benchmark')
parser.add_argument('--master_ip', default=None, type=str,
                    help='master ip for c10d')
parser.add_argument('--master_port', default=None, type=int,
                    help='master port for c10d')
# Pipeline parallelism
parser.add_argument('--micro-batch-size', type=int, default=None,
                    help='Batch size per model instance (local batch size).')
parser.add_argument('--global-batch-size', type=int,
                    default=256, help='Training batch size.')


def get_data_iterator(args):
    traindir = os.path.join(args.data, 'train')
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])

    train_dataset = datasets.ImageFolder(
        traindir,
        transforms.Compose([
            transforms.RandomResizedCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            normalize,
        ]))

    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.micro_batch_size, shuffle=True,
        num_workers=args.workers, pin_memory=True
    )
    data_iterator = iter(train_loader)
    return data_iterator


def train(args, data_iterator, model, optimizer, loss_func):
    for epoch in range(args.epochs):
        iteration = 0
        throughputs = []
        while True:
            try:
                start = time.time()
                optimizer.zero_grad()
                loss = pipedream_flush_schedule(
                    data_iterator, model, loss_func)
                optimizer.step()
                elapsed = time.time() - start

                iteration += 1
                if is_pipeline_last_stage() and iteration % args.print_freq == 0:
                    throughput = args.global_batch_size / elapsed
                    print("[Epoch {}/Iteration {}] loss: {:.2f} throughput: {:.0f} imgs/s".format(
                        epoch, iteration, loss, throughput
                    ))
                    throughputs.append(throughput)

                if iteration == args.benchmark_iters:
                    throughputs = np.array(throughputs)
                    print("Avg Throughput per 10 iterations: {:.2f} imgs/s, std: {:.2f} imgs/s".format(
                        np.mean(throughputs), np.std(throughputs)
                    ))
                    sys.exit()
            except StopIteration:
                break


def main():
    args = parser.parse_args()
    initialize_global_args(args)

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)

    torch.backends.cudnn.benchmark = True

    args.world_size = int(os.environ['WORLD_SIZE'])
    args.rank = int(os.environ['RANK'])
    args.local_rank = int(os.environ['LOCAL_RANK'])
    torch.cuda.set_device(args.local_rank)
    init_method = "tcp://{}:{}".format(args.master_ip, args.master_port)
    torch.distributed.init_process_group(
        'nccl', init_method=init_method,
        world_size=args.world_size, rank=args.rank,
        timeout=timedelta(seconds=10)
    )

    data_iterator = get_data_iterator(args)
    model = PipelineParallelResNet50(balance=[6, 5])
    model.cuda()

    optimizer = optim.SGD(model.parameters(), lr=0.1, momentum=0.9)
    loss_func = nn.CrossEntropyLoss().cuda()

    train(args, data_iterator, model, optimizer, loss_func)


if __name__ == '__main__':
    main()
