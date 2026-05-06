package compliance.authorization.resource.check.policy_0947

# Auto-generated policy 947
# Package: compliance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0947",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0947 {
    input.user.role == "admin"
}
denied_0947 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0947 = false

# Utility function for user info
