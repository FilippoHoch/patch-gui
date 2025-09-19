"""Binary diff fixtures used for integration tests."""

OLD_BYTES = b"hello\x00world"
NEW_BYTES = b"hello\x01world!"

BINARY_DIFF = """diff --git a/asset.bin b/asset.bin
index db12d84d7d09898766cc3d68c37aa7d58f6c3702..5e1ab517843d3789704d68ded6b8a204a4bf8726 100644
GIT binary patch
literal 12
Tcmc~u&B@7UEYB~>Nl^p<9k2vn

literal 11
Scmc~u&B@7UD9<m-NdW*EO9VXt
"""
