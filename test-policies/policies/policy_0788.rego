package governance.authentication.user.deny.policy_0788

# Auto-generated policy 788
# Package: governance.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0788",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0788 {
    input.user.active
    input.resource.public
}
allowed_0788 {
    input.user.role == "admin"
}
denied_0788 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0788 {
    data.policies.governance.enabled
}

# Utility function for user info
