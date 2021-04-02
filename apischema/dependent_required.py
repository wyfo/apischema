import warnings

from apischema.dependencies import dependent_required


def DependentRequired(*args, **kwargs):
    warnings.warn(
        "apischema.dependent_required.DependentRequired is deprecated,"
        " use apischema.dependent_required instead",
        DeprecationWarning,
    )
    return dependent_required(*args, **kwargs)
