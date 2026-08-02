"""User management service for Plex.

Provides high-level operations for:
- Retrieving user accounts and authentication status
- Viewing users associated with media items
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plexctl.models import UserAccount

if TYPE_CHECKING:
    from plexctl.client import PlexClient


class UserService:
    """Service for Plex user and authentication management.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def media_users(self, media_key: int | str) -> list[UserAccount]:
        """Get users who have played or interacted with a specific media item.

        Args:
            media_key: Plex rating key or id of media item.

        Returns:
            List[UserAccount]: List of UserAccount objects for users associated with the media.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        response = self._client.server.get(f"/library/metadata/{media_key}/users/top")  # type: ignore[attr-defined]
        data = response.json()

        # Parse users from MediaContainer wrapper
        container = data.get("MediaContainer", {})

        users = [
            UserAccount(
                id=int(item.get("id", 0)),
                username=item.get("username", ""),
                email=item.get("email", ""),
                friend=item.get("friend", False),
                restricted=item.get("restricted", False),
                doh=item.get("doh", False),
                anonymous=item.get("anonymous", False),
                title=item.get("title", ""),
                filtered=item.get("filtered", False),
                customAvatar=item.get("customAvatar", ""),
                joinedAt=item.get("joinedAt"),
            )
            for item in container.get("Account", []) or []
        ]

        return users
