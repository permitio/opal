package audit.enforcement.user.verify.policy_0988

# Auto-generated policy 988
# Package: audit.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0988",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0988 {
    data.policies.audit.enabled
}
denied_0988 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
