"""Where players can send feedback and support the project.

Fill in the values below to turn the buttons on: an empty value hides its button. The
GitHub issue links come from the update repo, so they always work.
"""
from __future__ import annotations

import sys

from . import __version__, i18n

CONTACT_EMAIL = ""        # e.g. "you@example.com": shows an "Email me" button
CONTACT_DISCORD = ""      # an invite or profile link: shows a "Discord" button
# Support links, shown in order: (button label, URL). The app stays free either way:
# no ads and no locked features.
SUPPORT_LINKS: list[tuple[str, str]] = [
    # ("Ko-fi", "https://ko-fi.com/yourname"),
    # ("Pix", "https://..."),
]


def info(cfg) -> dict:
    repo = f"https://github.com/{cfg.update_repo}"
    return {
        "version": __version__,
        "platform": sys.platform,
        "language": i18n.current(),
        "project_url": repo,
        "issues_url": f"{repo}/issues/new",
        "email": CONTACT_EMAIL or None,
        "discord": CONTACT_DISCORD or None,
        "support": [{"label": label, "url": url} for label, url in SUPPORT_LINKS if url],
    }
