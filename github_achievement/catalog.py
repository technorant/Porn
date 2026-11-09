from dataclasses import dataclass


@dataclass(frozen=True)
class Achievement:
    slug: str
    name: str
    thresholds: tuple[int, ...]
    description: str
    steps: tuple[str, ...]
    helper: bool = False


ACHIEVEMENTS = {
    item.slug: item for item in (
        Achievement("pull-shark", "Pull Shark", (2, 16, 128, 1024),
                    "Merged pull requests",
                    ("Create a temporary branch and activity commit", "Open and merge a pull request", "Delete the merged branch")),
        Achievement("pair-extraordinaire", "Pair Extraordinaire", (1, 10, 24, 48),
                    "Merged pull requests with a co-authored commit",
                    ("Verify the helper account and create a co-authored commit", "Confirm GitHub recognizes both authors, then merge the PR", "Verify the merge and delete the temporary branch"), True),
        Achievement("quickdraw", "Quickdraw", (1,),
                    "Close an issue within five minutes",
                    ("Open an issue", "Immediately close the issue")),
        Achievement("yolo", "YOLO", (1,),
                    "Merge a pull request without a review",
                    ("Create a branch, activity commit, and pull request", "Merge using the helper account without requesting review", "Delete the merged branch"), True),
        Achievement("galaxy-brain", "Galaxy Brain", (2, 8, 16, 32),
                    "Accepted answers in GitHub Discussions",
                    ("Helper opens a question in an answerable category", "Primary account posts an answer", "Helper marks that answer as accepted"), True),
    )
}

TIERS = {"base": 0, "bronze": 1, "silver": 2, "gold": 3}


def target_for(slug: str, tier: str) -> int:
    achievement = ACHIEVEMENTS[slug]
    index = TIERS[tier]
    if index >= len(achievement.thresholds):
        raise ValueError(f"{achievement.name} only has a base tier.")
    return achievement.thresholds[index]
