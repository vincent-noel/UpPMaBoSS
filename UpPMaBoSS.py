#!/usr/bin/env python

from sys import argv
from umbs import UpP_MaBoSS
from maboss import load
from os.path import exists, splitext

if __name__ == "__main__":

    if len(argv) < 4:
        print("Usage:\n")
        print("UpMaBoSS.py <file.bnd> <file.cfg> <file.upp>")
        exit(1)

    bnd_file = argv[1]
    cfg_file = argv[2]
    upp_file = argv[3]

    if not exists(bnd_file):
        print("Cannot find .bnd file")
        exit(1)

    if not exists(cfg_file):
        print("Cannot find .cfg file")
        exit(1)

    if not exists(upp_file):
        print("Cannot find .upp file")
        exit(1)

    workdir = splitext(cfg_file)[0]
    maboss_model = load(bnd_file, cfg_file)
    UpP_MaBoSS(maboss_model, upp_file, workdir, verbose=True)