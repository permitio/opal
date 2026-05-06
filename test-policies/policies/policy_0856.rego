package risk.authentication.user.deny.policy_0856

# Auto-generated policy 856
# Package: risk.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0856",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0856 = false
allowed_0856 {
    data.policies.risk.enabled
}
allowed_0856 {
    input.user.role == "admin"
}

# Utility function for user info
