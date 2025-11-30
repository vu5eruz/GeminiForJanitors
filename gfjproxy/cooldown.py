from dataclasses import dataclass
from itertools import groupby

from ._globals import COOLDOWN
from .bandwidth import BandwidthUsage, bandwidth_usage


@dataclass(frozen=True, kw_only=True)
class Cooldown:
    duration: int
    "Cooldown duration in seconds."

    bandwidth: int = 0
    "Bandwidth threshold in GiB"

    @staticmethod
    def parse(text: str) -> "Cooldown":
        if 0 < (index := text.find(":")):
            return Cooldown(
                duration=int(text[:index], base=10),
                bandwidth=int(text[index + 1 :], base=10),
            )
        if text:
            return Cooldown(duration=int(text, base=10))
        return Cooldown(duration=0)


@dataclass(frozen=True, kw_only=True)
class CooldownPolicy:
    cooldowns: list[Cooldown]

    def apply(self, usage: BandwidthUsage) -> int:
        bandwidth = usage.total // 1024
        for cooldown in self.cooldowns:
            if cooldown.bandwidth <= bandwidth:
                return cooldown.duration
        return 0

    @staticmethod
    def parse(text: str) -> "CooldownPolicy":
        cooldowns = [Cooldown.parse(step) for step in text.replace(" ", "").split(",")]
        cooldowns.sort(key=(lambda c: c.bandwidth), reverse=True)
        return CooldownPolicy(
            cooldowns=[
                max(group, key=lambda c: c.duration)
                for _, group in groupby(cooldowns, lambda c: c.bandwidth)
            ]
        )


cooldown_policy = CooldownPolicy.parse(COOLDOWN)


def get_cooldown(usage: BandwidthUsage | None = None) -> int:
    if usage is None:
        usage = bandwidth_usage()
    if not usage:
        return 0
    return cooldown_policy.apply(usage)
