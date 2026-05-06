package risk.validation.user.deny.policy_0579

# Auto-generated policy 579
# Package: risk.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0579",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0579 = false
denied_0579 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0579 {
    input.user.active
    input.resource.public
}

# Utility function for user info
