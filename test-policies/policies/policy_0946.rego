package audit.authentication.user.allow.policy_0946

# Auto-generated policy 946
# Package: audit.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0946",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0946 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0946 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0946 {
    data.policies.audit.enabled
}

# Utility function for user info
