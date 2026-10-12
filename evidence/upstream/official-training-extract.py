import copy
import time
from pathlib import Path
from textwrap import wrap

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import segmentation_models_pytorch as smp
import torch
import torch.nn.functional as F
import torch.optim as optim
import torchvision.transforms.v2 as v2
from segmentation_models_pytorch.losses import TverskyLoss
from torch.utils.data import DataLoader, Dataset
from torchvision import tv_tensors
from torchvision.transforms.functional import InterpolationMode

# set up parameters for training model
MC = 5  # number of Monte Carlo iterations (train/test splits)
patch_size = 128  # size of patches (inputs to model)
test_proportion = 0.5  # proportion of data to use for testing in each split
batch_size = 32
epochs = 5
init_lr = 1e-4
alpha = 0.2  # weight for false positives in Tversky loss
beta = 0.8  # weight for false negatives in Tversky loss

# image augmentations for training set
train_transform = v2.Compose(
    [
        v2.RandomResizedCrop(
            patch_size,
            scale=(0.5, 1.0),
            ratio=(0.75, 1.33),
            interpolation=InterpolationMode.BILINEAR,
        ),
        v2.RandomHorizontalFlip(p=0.5),
        v2.RandomVerticalFlip(p=0.5),
        v2.RandomRotation(30),
    ]
)

# set up arrays for output image
# pad image to be divisible by patch_size
pad = patch_size - np.array(X_orig.shape[:2]) % patch_size
y_viz = np.pad(
    y_orig, ((0, pad[0]), (0, pad[1])), mode="constant", constant_values=0
)  # y_viz is the padded version of y_orig used for compiling patches

# get shape of patchified version
patch_shape_labels = (patch_size, patch_size)
step = patch_size
y_patches = patchify(y_viz, patch_shape_labels, step)
y_out = np.zeros(y_patches.shape)

# train model over multiple Monte Carlo iterations
for mc in range(MC):
    print(f"Running Monte Carlo iteration {mc + 1}/{MC}...")

    # generate new dataset and create dataloaders
    X_train, y_train, X_test, y_test, test_inds = make_patches(
        X_orig, y_orig, patch_size, test_proportion=test_proportion, seed=10 * mc
    )
    X_train = X_train[:, good_channels, :, :]
    X_test = X_test[:, good_channels, :, :]

    train_dataset = ImageDataset(X_train, y_train, transform=None)
    train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_dataset = ImageDataset(X_test, tv_tensors.Mask(y_test), transform=None)
    test_dataloader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    # load UNet model from segmentation_models_pytorch
    in_channels = X_train.shape[1]
    out_channels = 1
    model = smp.Unet(
        encoder_name="resnet18",  # choose encoder, e.g. mobilenet_v2 or efficientnet-b7
        encoder_weights="imagenet",  # can use `imagenet` pre-trained weights for encoder initialization
        in_channels=in_channels,  # model input channels
        classes=out_channels,  # model output channels (number of classes in your dataset)
    ).to(device)

    # optimizer and loss function
    optimizer = optim.AdamW(model.parameters(), lr=init_lr)  # try adamw or others
    criterion = TverskyLoss(alpha=alpha, beta=beta, mode="binary")

    # track training and test losses
    train_batches = len(train_dataloader)
    test_batches = len(test_dataloader)
    train_losses = []
    test_losses = []

    # main training loop
    for epoch in range(epochs):
        # training loop
        model.train()
        running_loss = 0
        running_tversky = 0
        for i, (X, y) in enumerate(train_dataloader):
            # move data to device and apply transformations
            X = X.to(device)
            y = y.to(device)
            X, y = train_transform(X, tv_tensors.Mask(y))

            # compute prediction and loss
            outputs = model(X)[:, 0, :, :]
            train_loss = criterion(outputs, y[:, :, :])

            # backpropagation
            train_loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            # compute scoring metrics
            yp = F.sigmoid(outputs).squeeze()
            yt = y.squeeze().int()

            running_loss += train_loss.item()
        train_losses.append(running_loss / train_batches)

        # test loop
        model.eval()
        running_loss = 0
        with torch.no_grad():
            for i, (X, y) in enumerate(test_dataloader):
                X = X.to(device)
                y = y.to(device)
                outputs = model(X)[:, 0, :, :]

                # compute scoring metrics
                yp = F.sigmoid(outputs).squeeze()
                yt = y.squeeze().int()

                running_loss += criterion(outputs, y).item()
        test_losses.append(running_loss / test_batches)

        # save model if loss is lower than previous best
        if epoch == 0:
            best_loss = test_losses[-1]
            best_model = copy.deepcopy(model)
        elif test_losses[-1] < best_loss:
            best_loss = test_losses[-1]
            best_model = copy.deepcopy(model)

        # print epoch information
        print(f"epoch {epoch}")
        print(30 * "-")
        print(f"train loss: {train_losses[-1]}")
        print(f"test loss: {test_losses[-1]}")
        print(30 * "-")
        print(f"learning rate: {optimizer.param_groups[0]['lr']}")
        time.sleep(0.0001)

    # save prediction on test_inds on full image
    best_model.eval()
    test_preds = []
    with torch.no_grad():
        for i, (X, y) in enumerate(test_dataloader):
            X = X.to(device)
            y = y.to(device)
            outputs = best_model(X)[:, 0, :, :]

            # compute scoring metrics
            yp = F.sigmoid(outputs).squeeze()
            test_preds.append(yp.cpu())

    # add test predictions to y_out
    test_preds = torch.cat(test_preds, dim=0).numpy()
    for ii in range(len(test_inds)):
        y_out[test_inds[ii][0], test_inds[ii][1], :, :] += test_preds[ii] / MC

# output map from aggregated best models
y_combined = unpatchify(y_out, (y_viz.shape[0], y_viz.shape[1]))

