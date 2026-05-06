package risk.authentication.resource.deny.policy_0723

# Auto-generated policy 723
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0723",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0723 = false
allowed_0723 {
    input.user.active
    input.resource.public
}
allowed_0723 {
    input.user.role == "admin"
}
allowed_0723 {
    data.policies.risk.enabled
}

# Utility function for user info
