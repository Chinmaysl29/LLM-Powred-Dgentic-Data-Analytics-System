"""Distribution alerts require sufficient independent historical observations."""
from datetime import datetime, timedelta, timezone
import pytest
from backend.app.dataplane.config import Limits
from backend.app.dataplane.quality import profile, volume_baseline
from backend.tests.test_dataplane_engine import engine


def history(now, count):
    return [{'as_of': (now-timedelta(days=i)).isoformat(), 'row_count': 100,
             'columns': [{'column': 'amount', 'mean': -100, 'stddev': 1}]}
            for i in range(count, 0, -1)]


def test_f009_distribution_waits_for_distinct_historical_dates(engine):
    now = datetime.now(timezone.utc)
    for observations in (history(now, 1), history(now, 1)*8):
        result = profile(engine[0], observations, now.isoformat())
        assert result['distribution_warnings'] == []
    enough = profile(engine[0], history(now, 8), now.isoformat())
    assert enough['distribution_warnings']


def test_f009_distribution_threshold_is_configurable(engine):
    now = datetime.now(timezone.utc)
    engine[0].limits = Limits(monitoring_minimum_history=2, monitoring_history_window=4,
                             distribution_stddev_threshold=1000)
    assert profile(engine[0], history(now, 2), now.isoformat())['distribution_warnings'] == []


def test_f009_volume_threshold_and_history_are_configurable():
    now = datetime.now(timezone.utc)
    observations = [{'as_of': (now-timedelta(weeks=i)).isoformat(), 'row_count': v}
                    for i, v in enumerate((100, 110), 1)]
    limits = Limits(monitoring_minimum_history=2, monitoring_history_window=4, volume_mad_threshold=1)
    assert volume_baseline(115, observations, now, limits=limits)['status'] == 'warn'


def test_f009_history_window_cannot_be_smaller_than_minimum():
    with pytest.raises(ValueError, match='history'):
        Limits(monitoring_minimum_history=8, monitoring_history_window=2)
