package risk.authentication.resource.check.policy_0819

# Auto-generated policy 819
# Package: risk.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0819",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0819 {
    data.policies.risk.enabled
}
allowed_0819 {
    input.user.active
    input.resource.public
}
denied_0819 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
