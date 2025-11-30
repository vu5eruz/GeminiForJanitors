from gfjproxy.bandwidth import BandwidthUsage
from gfjproxy.cooldown import Cooldown, CooldownPolicy

################################################################################


def test_cooldown_parse_basic():
    """Basic cooldown parsing."""

    assert Cooldown.parse("") == Cooldown(duration=0)
    assert Cooldown.parse("0") == Cooldown(duration=0)
    assert Cooldown.parse("60") == Cooldown(duration=60)
    assert Cooldown.parse("120") == Cooldown(duration=120)


def test_cooldown_parse_extended():
    """Extended cooldown:bandwidth parsing."""

    assert Cooldown.parse("0:0") == Cooldown(duration=0)
    assert Cooldown.parse("60:0") == Cooldown(duration=60)
    assert Cooldown.parse("120:0") == Cooldown(duration=120)

    assert Cooldown.parse("0:100") == Cooldown(duration=0, bandwidth=100)
    assert Cooldown.parse("60:100") == Cooldown(duration=60, bandwidth=100)
    assert Cooldown.parse("120:100") == Cooldown(duration=120, bandwidth=100)


################################################################################


def test_cooldown_policy_parse():
    """Cooldown policy parsing."""

    assert CooldownPolicy.parse("") == CooldownPolicy(cooldowns=[Cooldown(duration=0)])
    assert CooldownPolicy.parse("0") == CooldownPolicy(cooldowns=[Cooldown(duration=0)])
    assert CooldownPolicy.parse("0:0") == CooldownPolicy(
        cooldowns=[Cooldown(duration=0)]
    )
    assert CooldownPolicy.parse("0:0, 0:0, 0:0") == CooldownPolicy(
        cooldowns=[Cooldown(duration=0)]
    )

    assert CooldownPolicy.parse("0:0, 1:0, 2:0") == CooldownPolicy(
        cooldowns=[Cooldown(duration=2)]
    )

    assert CooldownPolicy.parse("0:0, 1:1, 2:2") == CooldownPolicy(
        cooldowns=[
            Cooldown(duration=2, bandwidth=2),
            Cooldown(duration=1, bandwidth=1),
            Cooldown(duration=0, bandwidth=0),
        ]
    )

    assert CooldownPolicy.parse("0:0, 1:0, 0:1, 1:1, 0:2, 1:2") == CooldownPolicy(
        cooldowns=[
            Cooldown(duration=1, bandwidth=2),
            Cooldown(duration=1, bandwidth=1),
            Cooldown(duration=1, bandwidth=0),
        ]
    )

    # 60 s cooldown at 50 GiB bandwidth
    assert CooldownPolicy.parse("60:50") == CooldownPolicy(
        cooldowns=[
            Cooldown(duration=60, bandwidth=50),
        ]
    )

    # 30 s cooldown at 60 GiB bandwidth
    # 60 s cooldown at 75 GiB bandwidth
    # 90 s cooldown at 90 GiB bandwidth
    assert CooldownPolicy.parse("30:60, 60:75, 90:90") == CooldownPolicy(
        cooldowns=[
            Cooldown(duration=90, bandwidth=90),
            Cooldown(duration=60, bandwidth=75),
            Cooldown(duration=30, bandwidth=60),
        ]
    )


def test_cooldown_policy_apply():
    """Cooldown policy application."""

    policy = CooldownPolicy.parse("30:60, 60:75, 90:90")

    assert policy.apply(BandwidthUsage(total=0 * 1024)) == 0
    assert policy.apply(BandwidthUsage(total=60 * 1024)) == 30
    assert policy.apply(BandwidthUsage(total=75 * 1024)) == 60
    assert policy.apply(BandwidthUsage(total=90 * 1024)) == 90
    assert policy.apply(BandwidthUsage(total=100 * 1024)) == 90


################################################################################
