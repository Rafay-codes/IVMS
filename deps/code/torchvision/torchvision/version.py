__version__ = '0.12'
git_version = 'Unknown'
from torchvision.extension import _check_cuda_version
if _check_cuda_version() > 0:
    cuda = _check_cuda_version()
