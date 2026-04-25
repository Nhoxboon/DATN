"""Chat session management with Redis."""

import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from redis import Redis


class ChatMessage:
    """Chat message model."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        strategy: Optional[str] = None,
        strategy_reasoning: Optional[str] = None
    ):
        self.role = role  # "user" or "assistant"
        self.content = content
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.sources = sources or []
        self.strategy = strategy
        self.strategy_reasoning = strategy_reasoning

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "sources": self.sources,
            "strategy": self.strategy,
            "strategy_reasoning": self.strategy_reasoning
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        """Create from dictionary."""
        return cls(**data)


class ChatSession:
    """Chat session manager using Redis."""

    def __init__(self, redis_client: Redis, session_ttl: int = 86400):
        """
        Initialize chat session manager.

        Args:
            redis_client: Redis client instance
            session_ttl: Session TTL in seconds (default 24 hours)
        """
        self.redis = redis_client
        self.session_ttl = session_ttl

    def _get_session_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"chat:session:{session_id}:messages"

    def _get_metadata_key(self, session_id: str) -> str:
        """Get Redis key for session metadata."""
        return f"chat:session:{session_id}:metadata"

    def create_session(self) -> str:
        """
        Create a new chat session.

        Returns:
            Session ID (UUID)
        """
        session_id = str(uuid.uuid4())

        # Initialize metadata
        metadata = {
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
            "message_count": 0
        }

        metadata_key = self._get_metadata_key(session_id)
        self.redis.setex(
            metadata_key,
            self.session_ttl,
            json.dumps(metadata)
        )

        return session_id

    def add_message(
        self,
        session_id: str,
        message: ChatMessage
    ) -> None:
        """
        Add a message to the session.

        Args:
            session_id: Session ID
            message: Chat message to add
        """
        session_key = self._get_session_key(session_id)

        # Add message to list
        self.redis.rpush(session_key, json.dumps(message.to_dict()))

        # Update TTL
        self.redis.expire(session_key, self.session_ttl)

        # Update metadata
        metadata_key = self._get_metadata_key(session_id)
        metadata_json = self.redis.get(metadata_key)

        if metadata_json:
            metadata = json.loads(metadata_json)
            metadata["last_active"] = datetime.utcnow().isoformat()
            metadata["message_count"] = metadata.get("message_count", 0) + 1

            self.redis.setex(
                metadata_key,
                self.session_ttl,
                json.dumps(metadata)
            )

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """
        Get messages from a session.

        Args:
            session_id: Session ID
            limit: Optional limit on number of messages (most recent)

        Returns:
            List of chat messages
        """
        session_key = self._get_session_key(session_id)

        if limit:
            # Get last N messages
            messages_json = self.redis.lrange(session_key, -limit, -1)
        else:
            # Get all messages
            messages_json = self.redis.lrange(session_key, 0, -1)

        messages = [
            ChatMessage.from_dict(json.loads(msg))
            for msg in messages_json
        ]

        # Update last_active
        metadata_key = self._get_metadata_key(session_id)
        metadata_json = self.redis.get(metadata_key)

        if metadata_json:
            metadata = json.loads(metadata_json)
            metadata["last_active"] = datetime.utcnow().isoformat()
            self.redis.setex(
                metadata_key,
                self.session_ttl,
                json.dumps(metadata)
            )

        return messages

    def get_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session metadata.

        Args:
            session_id: Session ID

        Returns:
            Metadata dictionary or None if session doesn't exist
        """
        metadata_key = self._get_metadata_key(session_id)
        metadata_json = self.redis.get(metadata_key)

        if metadata_json:
            return json.loads(metadata_json)

        return None

    def session_exists(self, session_id: str) -> bool:
        """
        Check if session exists.

        Args:
            session_id: Session ID

        Returns:
            True if session exists
        """
        metadata_key = self._get_metadata_key(session_id)
        return self.redis.exists(metadata_key) > 0

    def clear_session(self, session_id: str) -> None:
        """
        Clear all messages from a session (for "New Chat").

        Args:
            session_id: Session ID
        """
        session_key = self._get_session_key(session_id)
        metadata_key = self._get_metadata_key(session_id)

        # Delete messages
        self.redis.delete(session_key)

        # Reset metadata
        metadata = {
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
            "message_count": 0
        }

        self.redis.setex(
            metadata_key,
            self.session_ttl,
            json.dumps(metadata)
        )

    def delete_session(self, session_id: str) -> None:
        """
        Delete a session completely.

        Args:
            session_id: Session ID
        """
        session_key = self._get_session_key(session_id)
        metadata_key = self._get_metadata_key(session_id)

        self.redis.delete(session_key, metadata_key)
