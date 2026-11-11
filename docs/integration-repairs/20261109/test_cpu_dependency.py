"""The shipped forecasting distribution must not bring GPU runtimes."""
from importlib.metadata import distributions, version


def test_f008_forecasting_uses_cpu_distribution_without_nvidia_runtime():
    import xgboost
    names = {d.metadata['Name'].lower().replace('_', '-') for d in distributions()}
    assert not any(name.startswith(('nvidia-', 'cuda-')) for name in names)
    assert version('xgboost-cpu') == xgboost.__version__
    assert not xgboost.build_info().get('USE_CUDA', False)
