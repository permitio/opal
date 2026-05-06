package governance.authentication.user.deny.policy_0763

# Auto-generated policy 763
# Package: governance.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0763",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0763 {
    data.policies.governance.enabled
}
denied_0763 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0763 {
    input.user.active
    input.resource.public
}
allowed_0763 {
    input.user.role == "admin"
}

# Utility function for user info
