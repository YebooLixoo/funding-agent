def test_new_models_importable():
    from web.models import (
        SystemSearchTerm, SystemFilterKeyword,
        BroadcastRecipient, UserEmailDelivery,
        SourceBootstrap, FetchHistory,
    )
    assert all([
        SystemSearchTerm, SystemFilterKeyword,
        BroadcastRecipient, UserEmailDelivery,
        SourceBootstrap, FetchHistory,
    ])
