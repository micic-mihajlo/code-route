"""Event system for async communication in Code Route."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from weakref import WeakSet


class EventType(str, Enum):
    """Event types for the event bus."""

    # Agent lifecycle events
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    AGENT_DELEGATED = "agent.delegated"

    # Tool lifecycle events
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_COMPLETED = "tool.completed"
    TOOL_ERROR = "tool.error"

    # Streaming events
    STREAM_START = "stream.start"
    STREAM_TOKEN = "stream.token"
    STREAM_COMPLETE = "stream.complete"

    # Memory events
    CONTEXT_UPDATED = "context.updated"
    MEMORY_STORED = "memory.stored"
    MEMORY_RETRIEVED = "memory.retrieved"

    # Conversation events
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_SENT = "message.sent"

    # System events
    SYSTEM_READY = "system.ready"
    SYSTEM_SHUTDOWN = "system.shutdown"
    ERROR = "error"


@dataclass
class Event:
    """An event in the system."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None  # Component that emitted the event

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = EventType(self.type)


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async event bus for pub/sub communication between components.

    Usage:
        bus = EventBus()

        async def on_tool_complete(event):
            print(f"Tool completed: {event.data}")

        bus.subscribe(EventType.TOOL_COMPLETED, on_tool_complete)
        await bus.publish(Event(EventType.TOOL_COMPLETED, {"result": "success"}))
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events."""
        if handler not in self._global_handlers:
            self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe from a specific event type."""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def unsubscribe_all(self, handler: EventHandler) -> None:
        """Unsubscribe from all events."""
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.

        Events are processed immediately (not queued) for low latency.
        """
        handlers = self._handlers.get(event.type, []) + self._global_handlers

        if handlers:
            # Run all handlers concurrently
            await asyncio.gather(
                *[self._safe_call(handler, event) for handler in handlers],
                return_exceptions=True
            )

    async def publish_nowait(self, event: Event) -> None:
        """
        Publish an event without waiting for handlers to complete.

        Useful for fire-and-forget events where latency matters.
        """
        handlers = self._handlers.get(event.type, []) + self._global_handlers

        for handler in handlers:
            asyncio.create_task(self._safe_call(handler, event))

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call handler with exception handling."""
        try:
            await handler(event)
        except Exception as e:
            # Emit error event (but don't recurse if this IS an error event)
            if event.type != EventType.ERROR:
                error_event = Event(
                    type=EventType.ERROR,
                    data={
                        "original_event": event.type.value,
                        "error": str(e),
                        "handler": handler.__name__,
                    },
                    source="EventBus"
                )
                await self.publish_nowait(error_event)

    def clear(self) -> None:
        """Clear all subscriptions."""
        self._handlers.clear()
        self._global_handlers.clear()


class EventEmitter:
    """
    Mixin class for components that emit events.

    Usage:
        class MyTool(BaseTool, EventEmitter):
            async def execute(self, **kwargs):
                await self.emit(EventType.TOOL_STARTED, {"name": self.name})
                # ... do work ...
                await self.emit(EventType.TOOL_COMPLETED, {"result": result})
    """

    _event_bus: Optional[EventBus] = None
    _source_name: Optional[str] = None

    def set_event_bus(self, bus: EventBus, source_name: Optional[str] = None) -> None:
        """Set the event bus for this emitter."""
        self._event_bus = bus
        self._source_name = source_name or self.__class__.__name__

    async def emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event if event bus is configured."""
        if self._event_bus:
            event = Event(
                type=event_type,
                data=data or {},
                source=self._source_name
            )
            await self._event_bus.publish_nowait(event)

    async def emit_and_wait(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event and wait for all handlers to complete."""
        if self._event_bus:
            event = Event(
                type=event_type,
                data=data or {},
                source=self._source_name
            )
            await self._event_bus.publish(event)
