package compliance.enforcement.context.verify.policy_0001

# Auto-generated policy 1
# Package: compliance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0001",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0001 = false
denied_0001 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0001 {
    data.policies.compliance.enabled
}

# Utility function for user info
