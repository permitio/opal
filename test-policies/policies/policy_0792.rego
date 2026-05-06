package risk.authentication.policy.verify.policy_0792

# Auto-generated policy 792
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0792",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0792 {
    data.policies.risk.enabled
}
allowed_0792 {
    input.user.role == "admin"
}
denied_0792 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0792 = false

# Utility function for user info
