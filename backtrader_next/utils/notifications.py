"""Broker notification delivery shared by preloaded and stepping engines."""


def notify_broker(engine):
    """Process the broker once and deliver events using the engine's policy."""
    engine._broker.next()
    notifications = engine._broker.notifs
    while notifications:
        order = notifications.popleft()
        owner = order.owner
        if owner is None:
            owner = engine.runningstrats[0]
        owner._addnotification(order, quicknotify=engine.p.quicknotify)
