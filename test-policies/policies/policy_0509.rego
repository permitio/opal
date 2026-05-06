package audit.enforcement.resource.deny.policy_0509

# Auto-generated policy 509
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0509",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0509 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0509 {
    input.user.role == "admin"
}

# Utility function for user info
