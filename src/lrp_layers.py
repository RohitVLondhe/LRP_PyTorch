"""Layers for layer-wise relevance propagation.

Layers for layer-wise relevance propagation can be modified.

"""
import torch
from torch import nn


def relevance_filter(r: torch.tensor, top_k_percent: float = 1.0) -> torch.tensor:
    """Filter that allows largest k percent values to pass for each batch dimension.

    Filter keeps k% of the largest tensor elements. Other tensor elements are set to
    zero. Here, k = 1 means that all relevance scores are passed on to the next layer.

    Args:
        r: Tensor holding relevance scores of current layer.
        top_k_percent: Proportion of top k values that is passed on.

    Returns:
        Tensor of same shape as input tensor.

    """
    assert 0.0 < top_k_percent <= 1.0

    if top_k_percent < 1.0:
        size = r.size()
        r = r.flatten(start_dim=1)
        num_elements = r.size(-1)
        k = max(1, int(top_k_percent * num_elements))
        top_k = torch.topk(input=r, k=k, dim=-1)
        r = torch.zeros_like(r)
        r.scatter_(dim=1, index=top_k.indices, src=top_k.values)
        return r.view(size)
    else:
        return r

class RelevancePropagationAdaptiveAvgPool2d(nn.Module):
    """Layer-wise relevance propagation for 2D adaptive average pooling.

    Attributes:
        layer: 2D adaptive average pooling layer.
        eps: A value added to the denominator for numerical stability.

    """

    def __init__(
        self,
        layer: torch.nn.AdaptiveAvgPool2d,
        eps: float = 1.0e-05,
        top_k: float = 0.0,
    ) -> None:
        super().__init__()
        self.layer = layer
        self.eps = eps
        self.top_k = top_k

    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        if self.top_k:
            r = relevance_filter(r, top_k_percent=self.top_k)
        z = self.layer.forward(a) + self.eps
        s = (r / z).data
        (z * s).sum().backward()
        c = a.grad
        r = (a * c).data
        return r


class RelevancePropagationAvgPool2d(nn.Module):
    """Layer-wise relevance propagation for 2D average pooling.

    Attributes:
        layer: 2D average pooling layer.
        eps: A value added to the denominator for numerical stability.

    """

    def __init__(
        self, layer: torch.nn.AvgPool2d, eps: float = 1.0e-05, top_k: float = 0.0
    ) -> None:
        super().__init__()
        self.layer = layer
        self.eps = eps
        self.top_k = top_k

    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        if self.top_k:
            r = relevance_filter(r, top_k_percent=self.top_k)
        z = self.layer.forward(a) + self.eps
        s = (r / z).data
        (z * s).sum().backward()
        c = a.grad
        r = (a * c).data
        return r


class RelevancePropagationMaxPool2d(nn.Module):
    """Layer-wise relevance propagation for 2D max pooling.

    Optionally substitutes max pooling by average pooling layers.

    Attributes:
        layer: 2D max pooling layer.
        eps: a value added to the denominator for numerical stability.

    """

    def __init__(
        self,
        layer: torch.nn.MaxPool2d,
        mode: str = "avg",
        eps: float = 1.0e-05,
        top_k: float = 0.0,
    ) -> None:
        super().__init__()

        if mode == "avg":
            self.layer = torch.nn.AvgPool2d(kernel_size=(2, 2))
        elif mode == "max":
            self.layer = layer

        self.eps = eps
        self.top_k = top_k

    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        if self.top_k:
            r = relevance_filter(r, top_k_percent=self.top_k)
        z = self.layer.forward(a) + self.eps
        s = (r / z).data
        (z * s).sum().backward()
        c = a.grad
        r = (a * c).data
        return r


class RelevancePropagationConv2d(nn.Module):
    """Layer-wise relevance propagation for 2D convolution.

    Optionally modifies layer weights according to propagation rule. Here z^+-rule

    Attributes:
        layer: 2D convolutional layer.
        eps: a value added to the denominator for numerical stability.

    """

    def __init__(
        self,
        layer: torch.nn.Conv2d,
        mode: str = "z_plus",
        eps: float = 1.0e-05,
        top_k: float = 0.0,
    ) -> None:
        super().__init__()

        self.layer = layer

        if mode == "z_plus":
            self.layer.weight = torch.nn.Parameter(self.layer.weight.clamp(min=0.0))
            self.layer.bias = torch.nn.Parameter(torch.zeros_like(self.layer.bias))

        self.eps = eps
        self.top_k = top_k

    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        if self.top_k:
            r = relevance_filter(r, top_k_percent=self.top_k)
        z = self.layer.forward(a) + self.eps
        s = (r / z).data
        (z * s).sum().backward()
        c = a.grad
        r = (a * c).data
        return r


class RelevancePropagationLinear(nn.Module):
    """Layer-wise relevance propagation for linear transformation.

    Optionally modifies layer weights according to propagation rule. Here z^+-rule

    Attributes:
        layer: linear transformation layer.
        eps: a value added to the denominator for numerical stability.

    """

    def __init__(
        self,
        layer: torch.nn.Linear,
        mode: str = "z_plus",
        eps: float = 1.0e-05,
        top_k: float = 0.0,
    ) -> None:
        super().__init__()

        self.layer = layer

        if mode == "z_plus":
            self.layer.weight = torch.nn.Parameter(self.layer.weight.clamp(min=0.0))
            self.layer.bias = torch.nn.Parameter(torch.zeros_like(self.layer.bias))

        self.eps = eps
        self.top_k = top_k

    @torch.no_grad()
    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        if self.top_k:
            r = relevance_filter(r, top_k_percent=self.top_k)
        z = self.layer.forward(a) + self.eps
        s = r / z
        c = torch.mm(s, self.layer.weight)
        r = (a * c).data
        return r


class RelevancePropagationFlatten(nn.Module):
    """Layer-wise relevance propagation for flatten operation.

    Attributes:
        layer: flatten layer.

    """

    def __init__(self, layer: torch.nn.Flatten, top_k: float = 0.0) -> None:
        super().__init__()
        self.layer = layer

    @torch.no_grad()
    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        r = r.view(size=a.shape)
        return r


class RelevancePropagationReLU(nn.Module):
    """Layer-wise relevance propagation for ReLU activation.

    Passes the relevance scores without modification. Might be of use later.

    """

    def __init__(self, layer: torch.nn.ReLU, top_k: float = 0.0) -> None:
        super().__init__()

    @torch.no_grad()
    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        return r


class RelevancePropagationDropout(nn.Module):
    """Layer-wise relevance propagation for dropout layer.

    Passes the relevance scores without modification. Might be of use later.

    """

    def __init__(self, layer: torch.nn.Dropout, top_k: float = 0.0) -> None:
        super().__init__()

    @torch.no_grad()
    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        return r


class RelevancePropagationIdentity(nn.Module):
    """Identity layer for relevance propagation.

    Passes relevance scores without modifying them.

    """

    def __init__(self, layer: nn.Module, top_k: float = 0.0) -> None:
        super().__init__()

    @torch.no_grad()
    def forward(self, a: torch.tensor, r: torch.tensor) -> torch.tensor:
        return r