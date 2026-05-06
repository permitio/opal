package compliance.enforcement.user.verify.policy_0466

# Auto-generated policy 466
# Package: compliance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0466",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0466 {
    input.user.role == "admin"
}
denied_0466 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0466 {
    data.policies.compliance.enabled
}
default allowed_0466 = false

# Utility function for user info
